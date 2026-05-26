import sys
import os
import time
import json
import sqlite3
import hashlib
from PyQt6.QtWidgets import (QMainWindow, QFileDialog, QApplication, QMenu, 
                             QStyledItemDelegate, QStyle, QListWidgetItem,
                             QCompleter, QMessageBox, QVBoxLayout, QWidget, QListWidget,
                             QLineEdit)
from PyQt6.QtGui import (QPixmap, QIcon, QAction, QStandardItemModel, 
                         QStandardItem, QColor, QPainter, QImageReader, QImage, QMovie,
                         QKeySequence, QShortcut)
from PyQt6.QtCore import (QDir, QUrl, Qt, QRect, QEvent, pyqtSignal, QTimer, 
                          QThread, QObject, QSize, QSortFilterProxyModel, QBuffer, QByteArray)

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

from Src.Ui.interface import MainWindowUI
from Src.Ui.theme import VSCODE_DARK_THEME
from Src.Logic.file_ops import FileContextMenu

# --- VIDEO THUMBNAILER (Native PyQt6) ---
class VideoThumbnailer(QObject):
    thumbnail_ready = pyqtSignal(str, QImage)

    def __init__(self):
        super().__init__()
        self.queue = []
        self.is_processing = False
        
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(0.0) 
        self.player.setAudioOutput(self.audio_output)
        
        self.sink = QVideoSink()
        self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self.on_frame_changed)
        
        self.current_path = None
        
        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self.on_timeout)

    def add_to_queue(self, paths):
        self.queue.extend(paths)
        if not self.is_processing:
            self.process_next()

    def clear_queue(self):
        self.queue.clear()
        self.player.stop()
        self.player.setSource(QUrl())
        self.timeout_timer.stop()
        self.is_processing = False
        self.current_path = None

    def process_next(self):
        # 🔹 Block processing if the worker is paused!
        if not self.queue or getattr(self, 'is_paused', False):
            self.is_processing = False
            self.current_path = None
            return
        
        self.is_processing = True
        self.current_path = self.queue.pop(0)
        
        try:
            if not os.path.exists(self.current_path) or os.path.getsize(self.current_path) < 100:
                self.current_path = None
                self.is_processing = False
                QTimer.singleShot(10, self.process_next)
                return
        except OSError:
            self.current_path = None
            self.is_processing = False
            QTimer.singleShot(10, self.process_next)
            return
        
        self.player.setSource(QUrl.fromLocalFile(self.current_path))
        QTimer.singleShot(30, self.player.play)
        self.timeout_timer.start(3000)

    # 🔹 PAUSE/RESUME LOGIC 🔹
    def pause(self):
        self.is_paused = True
        if self.is_processing:
            self.player.stop()
            self.timeout_timer.stop()
            self.is_processing = False
            # Put the video back in the queue so it doesn't get skipped!
            if getattr(self, 'current_path', None):
                self.queue.insert(0, self.current_path)
                self.current_path = None

    def resume(self):
        self.is_paused = False
        if not self.is_processing and self.queue:
            self.process_next()

    def on_frame_changed(self, frame):
        if not self.is_processing or not self.current_path:
            return
            
        image = frame.toImage()
        if image.isNull():
            return
            
        self.timeout_timer.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        path_to_emit = self.current_path
        self.current_path = None 
        
        TARGET_SIZE = 220
        scaled = image.scaled(TARGET_SIZE, TARGET_SIZE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        
        final_image = QImage(TARGET_SIZE, TARGET_SIZE, QImage.Format.Format_ARGB32)
        final_image.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(final_image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        x_pos = (TARGET_SIZE - scaled.width()) // 2
        y_pos = (TARGET_SIZE - scaled.height()) // 2
        painter.drawImage(x_pos, y_pos, scaled)
        
        painter.setPen(Qt.GlobalColor.white)
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.drawEllipse(10, 10, 30, 30)
        font = painter.font()
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(QRect(10, 10, 30, 30), Qt.AlignmentFlag.AlignCenter, "▶")
        painter.end()
        
        self.thumbnail_ready.emit(path_to_emit, final_image)
        QTimer.singleShot(10, self.process_next)

    def on_timeout(self):
        self.player.stop()
        self.player.setSource(QUrl())
        self.current_path = None
        self.process_next()

# ==========================================
# 🔹 MULTI-CORE IMAGE ENGINE
# ==========================================
class SingleThumbnailThread(QThread):
    """A single worker thread that decodes images."""
    thumbnail_ready = pyqtSignal(str, QImage)

    def __init__(self, perf_mode="balanced"):
        super().__init__()
        self.queue = []
        self.is_running = True
        self.is_paused = False
        self.perf_mode = perf_mode
        
        appdata_path = os.environ.get('APPDATA')
        if not appdata_path:
            appdata_path = os.path.expanduser('~')
        self.cache_dir = os.path.join(appdata_path, 'MediaNest', 'ThumbCache')
        os.makedirs(self.cache_dir, exist_ok=True)

    def add_to_queue(self, path_list):
        self.queue.extend(path_list)

    def clear_queue(self):
        self.queue.clear()

    def pause(self):
        self.is_paused = True

    def resume(self):
        self.is_paused = False

    def run(self):
        TARGET_SIZE = 220
        
        if self.perf_mode == "high":
            hdd_sleep = 0.001   
        elif self.perf_mode == "low":
            hdd_sleep = 0.080   
        else:
            hdd_sleep = 0.015   

        while self.is_running:
            if self.is_paused or not self.queue:
                time.sleep(0.1)
                continue

            try:
                path = self.queue.pop(0)
            except IndexError:
                continue

            is_gallery = os.path.isdir(path)
            target_path = path
            
            if is_gallery:
                # Find the first image in the directory
                try:
                    for entry in os.scandir(path):
                        if entry.is_file() and entry.name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                            target_path = entry.path
                            break
                except OSError:
                    pass

            # 1. CHECK CACHE
            path_hash = hashlib.md5(path.encode('utf-8')).hexdigest()
            cache_file_path = os.path.join(self.cache_dir, f"{path_hash}.jpg")

            if os.path.exists(cache_file_path):
                cached_image = QImage(cache_file_path)
                if not cached_image.isNull():
                    self.thumbnail_ready.emit(path, cached_image)
                    time.sleep(0.005)
                    continue

            # 2. GENERATE NEW
            try:
                reader = QImageReader(target_path)
                orig_size = reader.size()

                if orig_size.isValid():
                    ratio = min(TARGET_SIZE / orig_size.width(), TARGET_SIZE / orig_size.height())
                    new_w = int(orig_size.width() * ratio)
                    new_h = int(orig_size.height() * ratio)
                    reader.setScaledSize(QSize(new_w, new_h))

                loaded_image = reader.read()
                del reader
                
                if not loaded_image.isNull():
                    final_image = QImage(TARGET_SIZE, TARGET_SIZE, QImage.Format.Format_ARGB32)
                    final_image.fill(Qt.GlobalColor.transparent)

                    painter = QPainter(final_image)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    
                    if is_gallery:
                        # Draw stacked paper effect for galleries
                        w = loaded_image.width()
                        h = loaded_image.height()
                        
                        # Layer 1 (Bottom, tilted left)
                        painter.save()
                        painter.translate(TARGET_SIZE//2 - 6, TARGET_SIZE//2 + 8)
                        painter.rotate(-12)
                        painter.fillRect(QRect(-w//2, -h//2, w, h), Qt.GlobalColor.white)
                        painter.setPen(QColor(0, 0, 0, 70))
                        painter.drawRect(QRect(-w//2, -h//2, w, h))
                        painter.restore()
                        
                        # Layer 2 (Middle, tilted right)
                        painter.save()
                        painter.translate(TARGET_SIZE//2 + 8, TARGET_SIZE//2 - 4)
                        painter.rotate(9)
                        painter.fillRect(QRect(-w//2, -h//2, w, h), Qt.GlobalColor.white)
                        painter.setPen(QColor(0, 0, 0, 70))
                        painter.drawRect(QRect(-w//2, -h//2, w, h))
                        painter.restore()

                        # Layer 3 (Top-ish, slightly tilted)
                        painter.save()
                        painter.translate(TARGET_SIZE//2 - 3, TARGET_SIZE//2 - 6)
                        painter.rotate(-4)
                        painter.fillRect(QRect(-w//2, -h//2, w, h), Qt.GlobalColor.white)
                        painter.setPen(QColor(0, 0, 0, 70))
                        painter.drawRect(QRect(-w//2, -h//2, w, h))
                        painter.restore()

                    x_pos = (TARGET_SIZE - loaded_image.width()) // 2
                    y_pos = (TARGET_SIZE - loaded_image.height()) // 2
                    painter.drawImage(x_pos, y_pos, loaded_image)
                    
                    if is_gallery:
                        painter.setPen(QColor(0, 0, 0, 50))
                        painter.drawRect(x_pos, y_pos, loaded_image.width(), loaded_image.height())
                        
                    painter.end()

                    final_image.save(cache_file_path, "JPG", 85)
                    self.thumbnail_ready.emit(path, final_image)
            except Exception:
                pass

            time.sleep(hdd_sleep)

    def stop(self):
        self.is_running = False
        self.wait()


class ThumbnailWorker(QObject):
    """The Brain: Manages the swarm of worker threads and distributes the load."""
    thumbnail_ready = pyqtSignal(str, QImage)

    def __init__(self, perf_mode="balanced"):
        super().__init__()
        self.perf_mode = perf_mode
        
        # 🔹 DYNAMIC CORE ALLOCATION
        if perf_mode == "high":
            self.thread_count = 8   # Load 8 images simultaneously!
        elif perf_mode == "low":
            self.thread_count = 1   # Power saver (Safe for older laptops)
        else:
            self.thread_count = 4   # Balanced (4 images at once)
            
        self.threads = []
        self.current_idx = 0

        for _ in range(self.thread_count):
            t = SingleThumbnailThread(perf_mode)
            t.thumbnail_ready.connect(self.thumbnail_ready.emit)
            self.threads.append(t)

    # Mimic QThread commands so the rest of the app doesn't break!
    def start(self):
        for t in self.threads:
            t.start()

    def setPriority(self, priority):
        for t in self.threads:
            t.setPriority(priority)

    def add_to_queue(self, path_list):
        # Round-robin distribution: Deal the images like cards to all active threads!
        for path in path_list:
            self.threads[self.current_idx].add_to_queue([path])
            self.current_idx = (self.current_idx + 1) % self.thread_count

    def clear_queue(self):
        for t in self.threads:
            t.clear_queue()

    def pause(self):
        for t in self.threads:
            t.pause()

    def resume(self):
        for t in self.threads:
            t.resume()

    def stop(self):
        for t in self.threads:
            t.stop()

    # Smartly intercepts any attempts by the main app to modify the queue directly
    @property
    def queue(self):
        return [p for t in self.threads for p in t.queue]
        
    @queue.setter
    def queue(self, new_queue):
        self.clear_queue()
        self.add_to_queue(new_queue)

class DatabaseSearchWorker(QThread):
    # Added 'int' at the end to return the search_id
    search_finished = pyqtSignal(list, dict, str, bool, int) 
    error_occurred = pyqtSignal(str)

    def __init__(self, db_path, search_text, limit, offset, search_id, filter_type="All"): # 👈 ADDED HERE
        super().__init__()
        self.db_path = db_path
        self.search_text = search_text
        self.limit = limit
        self.offset = offset
        self.search_id = search_id
        self.filter_type = filter_type
        self.is_running = True

    def run(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            raw_tags = [t.strip() for t in self.search_text.split(',') if t.strip()]
            req_tags, opt_tags = [], []

            for t in raw_tags:
                is_or = t.startswith('~')
                clean_tag = t[1:].strip() if is_or else t
                clean_tag = clean_tag.replace(' ', '_')
                if clean_tag:
                    if is_or: opt_tags.append(clean_tag)
                    else: req_tags.append(clean_tag)

            all_tags = req_tags + opt_tags

            if not all_tags:
                self.search_finished.emit([], {}, self.search_text, False, self.search_id)
                return

            placeholders = ', '.join(['?'] * len(all_tags))
            file_filter_sql = ""
            if self.filter_type == "Images":
                file_filter_sql = " AND (Images.file_name LIKE '%.jpg' OR Images.file_name LIKE '%.jpeg' OR Images.file_name LIKE '%.png' OR Images.file_name LIKE '%.gif' OR Images.file_name LIKE '%.bmp' OR Images.file_name LIKE '%.webp')"
            elif self.filter_type == "Videos":
                file_filter_sql = " AND (Images.file_name LIKE '%.mp4' OR Images.file_name LIKE '%.mkv' OR Images.file_name LIKE '%.avi' OR Images.file_name LIKE '%.mov' OR Images.file_name LIKE '%.webm')"
            query = f"""
                SELECT Images.file_path, Images.file_name 
                FROM Images
                JOIN ImageTags ON Images.hash = ImageTags.hash
                JOIN Tags ON ImageTags.tag_id = Tags.tag_id
                WHERE Tags.tag_name IN ({placeholders})
                GROUP BY Images.hash
                HAVING 1=1
            """
            params = all_tags.copy()

            if req_tags:
                req_placeholders = ', '.join(['?'] * len(req_tags))
                query += f" AND SUM(CASE WHEN Tags.tag_name IN ({req_placeholders}) THEN 1 ELSE 0 END) = ?"
                params.extend(req_tags)
                params.append(len(req_tags))

            if opt_tags:
                opt_placeholders = ', '.join(['?'] * len(opt_tags))
                query += f" AND SUM(CASE WHEN Tags.tag_name IN ({opt_placeholders}) THEN 1 ELSE 0 END) > 0"
                params.extend(opt_tags)
            query += " ORDER BY Images.phash"
            query += " LIMIT ? OFFSET ?"
            params.extend([self.limit, self.offset])

            cursor.execute(query, params)
            results = cursor.fetchall()

            from collections import defaultdict
            folders_map = defaultdict(list)
            valid_results = []

            for file_path, file_name in results:
                if not self.is_running: return
                if os.path.exists(file_path):
                    folder_name = os.path.basename(os.path.dirname(file_path))
                    folders_map[folder_name].append((file_path, file_name, "image"))
                    valid_results.append((file_path, file_name, "image"))

            # --- MANGA GALLERIES SEARCH ---
            if self.filter_type in ["All", "Images"]:
                manga_query = f"""
                    WITH GalleryAllTags AS (
                        SELECT MangaTags.gallery_id, Tags.tag_name as tag
                        FROM MangaTags
                        JOIN Tags ON MangaTags.tag_id = Tags.tag_id
                        UNION
                        SELECT gallery_id, artist as tag
                        FROM MangaGalleries
                        WHERE artist IS NOT NULL AND artist != ''
                    )
                    SELECT MangaGalleries.folder_path, MangaGalleries.title 
                    FROM MangaGalleries
                    JOIN GalleryAllTags ON MangaGalleries.gallery_id = GalleryAllTags.gallery_id
                    WHERE GalleryAllTags.tag IN ({placeholders})
                    GROUP BY MangaGalleries.gallery_id
                    HAVING 1=1
                """
                manga_params = all_tags.copy()
                if req_tags:
                    manga_query += f" AND SUM(CASE WHEN GalleryAllTags.tag IN ({req_placeholders}) THEN 1 ELSE 0 END) = ?"
                    manga_params.extend(req_tags)
                    manga_params.append(len(req_tags))
                if opt_tags:
                    manga_query += f" AND SUM(CASE WHEN GalleryAllTags.tag IN ({opt_placeholders}) THEN 1 ELSE 0 END) > 0"
                    manga_params.extend(opt_tags)
                manga_query += " LIMIT ? OFFSET ?"
                manga_params.extend([self.limit, self.offset])

                try:
                    cursor.execute(manga_query, manga_params)
                    manga_results = cursor.fetchall()
                    for folder_path, title in manga_results:
                        if not self.is_running: return
                        if os.path.exists(folder_path):
                            # Append directly to valid results
                            valid_results.append((folder_path, title, "gallery"))
                except sqlite3.OperationalError:
                    pass # MangaGalleries table might not exist yet

            is_appending = self.offset > 0
            self.search_finished.emit(valid_results, dict(folders_map), self.search_text, is_appending, self.search_id)
            conn.close()

        except Exception as e:
            self.error_occurred.emit(str(e))

    def stop(self):
        self.is_running = False

class SmartTreeFilter(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.search_text = ""

    def set_search_text(self, text):
        self.search_text = text.lower()
        self.invalidateFilter()  

    def filterAcceptsRow(self, source_row, source_parent):
        if not self.search_text:
            return True

        source_model = self.sourceModel()
        index = source_model.index(source_row, 0, source_parent)
        item = source_model.itemFromIndex(index)
        
        if not item: 
            return False

        item_text = item.text().lower()

        if "loading..." in item_text:
            return True

        if self.search_text in item_text:
            return True

        parent_idx = index.parent()
        while parent_idx.isValid():
            parent_item = source_model.itemFromIndex(parent_idx)
            if parent_item and self.search_text in parent_item.text().lower():
                return True
            parent_idx = parent_idx.parent()

        def has_matching_child(idx):
            for i in range(source_model.rowCount(idx)):
                child_idx = source_model.index(i, 0, idx)
                child_item = source_model.itemFromIndex(child_idx)
                if child_item:
                    if self.search_text in child_item.text().lower():
                        return True
                    if has_matching_child(child_idx):
                        return True
            return False

        if has_matching_child(index):
            return True

        return False

# --- CUSTOM MULTI-TAG COMPLETER ---
class MultiTagCompleter(QCompleter):
    def __init__(self, tags, parent=None):
        super().__init__(tags, parent)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterMode(Qt.MatchFlag.MatchContains) 

    def showPopup(self):
        # 1. Let PyQt generate the popup normally first
        super().showPopup()
        
        popup = self.popup()
        search_bar = self.widget()
        
        if popup and search_bar:
            from PyQt6.QtCore import QPoint
            
            # 2. Get the absolute coordinates of the bottom-left of the search bar
            global_pos = search_bar.mapToGlobal(QPoint(0, search_bar.height()))
            
            # 3. Forcibly move the popup to these exact coordinates every time
            # This overrides Qt's tendency to throw it to Monitor 1 during full-screen
            popup.move(global_pos)
            
            # 4. Lock the width to perfectly match the search bar
            popup.setFixedWidth(search_bar.width())

    def pathFromIndex(self, index):
        suggestion = super().pathFromIndex(index)
        current_text = self.widget().text()
        
        if ',' in current_text:
            prefix = current_text[:current_text.rfind(',')]
            last_word = current_text.split(',')[-1].strip()
            
            # Put the tilde back if the user typed it for this specific word!
            if last_word.startswith('~'):
                return f"{prefix}, ~{suggestion}"
            return f"{prefix}, {suggestion}"
        
        if current_text.strip().startswith('~'):
            return f"~{suggestion}"
            
        return suggestion

    def splitPath(self, path):
        if ',' in path:
            search_term = path.split(',')[-1].strip()
        else:
            search_term = path.strip()
            
        if search_term.startswith('~'):
            search_term = search_term[1:]
            
        search_term = search_term.replace(' ', '_')
        return [search_term]

# --- SCANNER WORKER ---
class ScannerWorker(QThread):
    batch_found = pyqtSignal(str, list)
    finished = pyqtSignal()

    def __init__(self, folder_path, img_exts, vid_exts):
        super().__init__()
        self.folder_path = folder_path
        self.img_exts = img_exts
        self.vid_exts = vid_exts
        self.is_running = True

    def run(self):
        batch = []
        for root, dirs, files in os.walk(self.folder_path):
            if not self.is_running: break
            for file in files:
                if not self.is_running: break
                
                name = file.lower()
                is_img = any(name.endswith(e) for e in self.img_exts)
                is_vid = any(name.endswith(e) for e in self.vid_exts)

                if is_img or is_vid:
                    full_path = os.path.join(root, file)
                    
                    # 🔹 FIX: Skip 0-byte or heavily corrupted ghost files
                    try:
                        if os.path.getsize(full_path) < 100:  
                            continue
                    except OSError:
                        continue
                        
                    rel_path = os.path.relpath(full_path, self.folder_path)
                    display_name = rel_path.replace("\\", " > ")
                    batch.append( (display_name, full_path, is_vid) )

                    if len(batch) >= 50: 
                        self.batch_found.emit(self.folder_path, batch)
                        batch = []
                        self.msleep(10)

        if batch: self.batch_found.emit(self.folder_path, batch)
        self.finished.emit()

    def stop(self):
        self.is_running = False

# --- DELEGATE ---
class FolderButtonDelegate(QStyledItemDelegate):
    button_clicked = pyqtSignal(object)
   
    def paint(self, painter, option, index):
        # Draw default item first (text, selection, highlight)
        super().paint(painter, option, index)

        # Check if this item should show folder toggle icon
        is_folder = index.data(Qt.ItemDataRole.UserRole + 2)
        has_subfolders = index.data(Qt.ItemDataRole.UserRole + 6)
        is_flat_root = index.data(Qt.ItemDataRole.UserRole + 4)

        if not ((is_folder and has_subfolders) or is_flat_root):
            return

        # Get main window to access icons
        main_window = self.parent().window()

        if not hasattr(main_window, "icon_folder_closed"):
            return

        # Determine open/close state
        is_open = index.data(Qt.ItemDataRole.UserRole + 30)

        icon = (
            main_window.icon_folder_open
            if is_open
            else main_window.icon_folder_closed
        )

        pixmap = icon.pixmap(
            20,
            20
        )

        # Define right-side icon area
        button_rect = QRect(
            option.rect.right() - 30,
            option.rect.top(),
            30,
            option.rect.height()
        )

        painter.save()

        # Center icon inside button rect
        x = button_rect.x() + (button_rect.width() - pixmap.width()) // 2
        y = button_rect.y() + (button_rect.height() - pixmap.height()) // 2

        painter.drawPixmap(x, y, pixmap)

        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease:
            is_folder = index.data(Qt.ItemDataRole.UserRole + 2)
            has_subfolders = index.data(Qt.ItemDataRole.UserRole + 6)
            is_flat_root = index.data(Qt.ItemDataRole.UserRole + 4)
            if (is_folder and has_subfolders) or is_flat_root:
                 click_x = event.position().x()
                 if click_x > option.rect.right() - 30:
                     self.button_clicked.emit(index)
                     return True 
        return False

class FloatingViewerWindow(QWidget):
    """A standalone window designed to hold the media player for multi-monitor use."""
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.setWindowTitle("Media Nest - Detached Viewer")
        self.setMinimumSize(800, 600)
        
        # Apply the VS Code Dark theme to the floating window
        from Src.Ui.theme import VSCODE_DARK_THEME
        self.setStyleSheet(VSCODE_DARK_THEME)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

    def closeEvent(self, event):
        # When the user clicks the 'X' on this detached window,
        # tell the main app to pull the media player back!
        self.main_app.reattach_viewer()
        event.accept()

# --- MAIN APP ---
class MediaExplorerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self._is_toggling_fullscreen = False
        self.ui = MainWindowUI()
        self.image_cache = {}
        self.ui.setup_ui(self)
        self.setWindowTitle("Media Nest V2.0.0")
        # --- DYNAMIC TEXT SCALING FIX ---
        theme = VSCODE_DARK_THEME
        
        try:
            # Grab the scale factor we set in main.py
            current_scale = float(os.environ.get("QT_SCALE_FACTOR", "1.0"))
            
            # If the scale is 90% (0.9) or lower, force bold white text!
            if current_scale < 1.0:
                theme += """
                    QWidget { 
                        font-weight: bold; 
                        color: #ffffff; 
                    }
                    QTreeView, QListView { 
                        font-weight: bold; 
                    }
                """
        except Exception:
            pass # Failsafe in case the scale variable isn't found
            
        self.setStyleSheet(theme)
        # --------------------------------

        # Setup icon loader helper
        from Src.Logic.paths import resource_path
        self.asset_dir = resource_path("assets")
        self.get_icon = lambda name: QIcon(
            os.path.join(self.asset_dir, "Svg", f"{name}.svg")
        )            

        logo_path = os.path.join(self.asset_dir, "Logo.ico")
        self.setWindowIcon(QIcon(logo_path))

        self.image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp', '*.webp']
        self.video_extensions = ['*.mp4', '*.mkv', '*.avi', '*.mov', '*.webm']
        self.clean_img_exts = [e.replace("*", "") for e in self.image_extensions]
        self.clean_vid_exts = [e.replace("*", "") for e in self.video_extensions]

        # --- STATE VARIABLES ---
        self.is_video_looping = False
        self.is_muted = False
        self.previous_volume = 100
        self.is_video_maximized = False

        self.setup_media_player()
        self.ui.video_widget.skip_forward_signal.connect(self.skip_forward)
        self.ui.video_widget.skip_backward_signal.connect(self.skip_backward)
        self.ui.video_widget.toggle_play_signal.connect(self.toggle_play_pause)
        
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["Name"])

        self.proxy_model = SmartTreeFilter()
        self.proxy_model.setSourceModel(self.model)        
        self.ui.tree_view.setModel(self.proxy_model)
        
        # --- SEARCH DEBOUNCE TIMER ---
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300) # Wait 300ms after the last input before searching
        self.search_timer.timeout.connect(self.process_search)
        self.clear_player_timer = QTimer(self)
        self.clear_player_timer.setSingleShot(True) 
        self.clear_player_timer.timeout.connect(self.clear_media_viewer)

        self.ui.search_bar.textChanged.connect(self.on_search_bar_typed)
        self.ui.search_bar.returnPressed.connect(self.force_instant_search)

        self.delegate = FolderButtonDelegate(self.ui.tree_view)
        self.delegate.button_clicked.connect(self.on_folder_toggle)
        self.ui.tree_view.setItemDelegate(self.delegate)

        self.ui.btn_open.clicked.connect(self.open_folder_dialog)
        self.db_connection = None 
        self.ui.btn_load_db.clicked.connect(self.auto_load_database)
        self.ui.btn_change_db.clicked.connect(self.open_settings_dialog)        
        self.ui.btn_detach.clicked.connect(self.toggle_detached_viewer)
        self.floating_viewer = None
        self.ui.tree_view.expanded.connect(self.on_item_expanded)
        self.ui.tree_view.clicked.connect(self.on_tree_item_clicked)
        
        self.ui.gallery_section.list_widget.currentItemChanged.connect(self.on_gallery_item_changed)
        if hasattr(self.ui.gallery_section, 'filter_combo'):
            self.ui.gallery_section.filter_combo.currentTextChanged.connect(self.on_filter_changed)
        if hasattr(self.ui.gallery_section, 'name_filter_input'):
            self.ui.gallery_section.name_filter_input.textChanged.connect(self.apply_gallery_filter)
        self.current_image_path = None
        
        # This skips thousands of scrollbar math calculations.
        self.ui.gallery_section.list_widget.setUniformItemSizes(True)
        self.ui.gallery_section.list_widget.setGridSize(QSize(250, 270))
        self.ui.gallery_section.list_widget.setLayoutMode(QListWidget.LayoutMode.Batched)
        self.ui.gallery_section.list_widget.setBatchSize(50)
        
        # 🔹 CONNECT THE SCROLLBAR LISTENER
        self.ui.gallery_section.list_widget.verticalScrollBar().valueChanged.connect(self.on_gallery_scroll)
        self.is_fetching_data = False 
        
        self.current_gallery_folder = None 
        self.scanner_thread = None
        self.loading_item_ref = None 
        
        self.current_search_offset = 0
        self.current_search_id = 0  # Tracks which search is active to prevent ghost-appending

        # ==========================================
        # 🔹 PERFORMANCE MODE INITIALIZATION
        # ==========================================
        import json
        perf_mode = "balanced"
        
        # Safely locate and read the config file
        import sys
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.abspath(".") 
            
        config_path = os.path.join(base_dir, "config.json")
        
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    perf_mode = config.get("performance_mode", "balanced")
            except Exception:
                pass
        self.current_perf_mode = perf_mode
        self.thumbnail_map = {} 
        self.thumb_worker = ThumbnailWorker(perf_mode=perf_mode)
        self.thumb_worker.thumbnail_ready.connect(self.on_thumbnail_ready)
        self.thumb_worker.start()
        
        # 🔹 DYNAMIC CPU PRIORITY
        # If High Performance is selected, let the CPU dedicate maximum power to thumbnails.
        # If Low/Balanced is selected, force it to the background so the UI doesn't lag.
        if perf_mode == "high":
            self.thumb_worker.setPriority(QThread.Priority.HighestPriority)
        elif perf_mode == "low":
            self.thumb_worker.setPriority(QThread.Priority.LowestPriority)
        else:
            self.thumb_worker.setPriority(QThread.Priority.LowPriority)
        
        # Initialize Video Worker
        self.vid_thumb_worker = VideoThumbnailer()
        self.vid_thumb_worker.thumbnail_ready.connect(self.on_thumbnail_ready)
        self.pending_thumbnails = {}
        self.thumbnail_apply_timer = QTimer(self)
        self.thumbnail_apply_timer.timeout.connect(self.apply_pending_thumbnails)
        self.thumbnail_apply_timer.start(100)
        self.autohide_timer = QTimer(self)
        self.autohide_timer.setInterval(3000)
        self.autohide_timer.timeout.connect(self.hide_fullscreen_controls)
        self.was_maximized = False
        QApplication.instance().installEventFilter(self)       
        self.icon_folder_closed = QIcon(os.path.join(self.asset_dir, "Svg", "folder-close.svg"))
        self.icon_folder_open = QIcon(os.path.join(self.asset_dir, "Svg", "folder-open.svg")) 
        self.file_ops = FileContextMenu(self)
        self.ui.gallery_section.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.gallery_section.list_widget.customContextMenuRequested.connect(self.show_gallery_context_menu)
        self.ui.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tree_view.customContextMenuRequested.connect(self.show_tree_context_menu)

    def closeEvent(self, event):
        """Fires exactly when the user clicks the 'X' to close the app."""
        # 1. Stop the Main Media Player safely
        if hasattr(self, 'media_player'):
            self.media_player.stop()
            
        # 2. Kill the Image Thumbnail Worker (This one IS a QThread)
        if hasattr(self, 'thumb_worker'):
            self.thumb_worker.stop()

        # 3. Kill the Video Thumbnail Worker (This one is a QObject with a hidden media player)
        if hasattr(self, 'vid_thumb_worker'):
            self.vid_thumb_worker.queue.clear()
            self.vid_thumb_worker.is_processing = False
            if hasattr(self.vid_thumb_worker, 'player'):
                self.vid_thumb_worker.player.stop()
            if hasattr(self.vid_thumb_worker, 'timeout_timer'):
                self.vid_thumb_worker.timeout_timer.stop()

        # 4. Stop background database searches
        if hasattr(self, 'db_search_worker') and self.db_search_worker.isRunning():
            self.db_search_worker.is_running = False
            self.db_search_worker.quit()
            self.db_search_worker.wait(1000)
            
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def setup_media_player(self):
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.ui.video_widget)

        # Hook up UI Controls
        self.ui.btn_play.clicked.connect(self.toggle_play_pause)
        self.ui.btn_skip_backward.clicked.connect(self.skip_backward)
        self.ui.btn_skip_forward.clicked.connect(self.skip_forward)
        self.ui.btn_fullscreen.clicked.connect(self.toggle_fullscreen)        
        
        # New Hooks for Volume and Loop
        self.ui.btn_loop.clicked.connect(self.toggle_loop)
        self.ui.slider_volume.valueChanged.connect(self.set_volume)
        self.ui.btn_volume.clicked.connect(self.toggle_mute)
        self.media_player.mediaStatusChanged.connect(self.media_status_changed)

        self.media_player.playbackStateChanged.connect(self.media_state_changed)
        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.durationChanged.connect(self.duration_changed)
        self.ui.slider_progress.sliderMoved.connect(self.set_position)
        self.ui.btn_previous.clicked.connect(self.play_previous)
        self.ui.btn_next.clicked.connect(self.play_next)

    def toggle_loop(self):
        self.is_video_looping = not self.is_video_looping

        if self.is_video_looping:
            # Use colored version permanently
            self.ui.btn_loop.setIcon(
                QIcon(os.path.join(self.asset_dir, "Svg2", "repeat.svg"))
            )
        else:
            self.ui.btn_loop.setIcon(
                QIcon(os.path.join(self.asset_dir, "Svg", "repeat-off.svg"))
            )

    def media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.is_video_looping:
                self.media_player.setPosition(0) 
                self.media_player.play()         

    def toggle_detached_viewer(self):
        """Switches the player between the main window and the floating window."""
        if self.floating_viewer is None:
            self.detach_viewer()
        else:
            self.reattach_viewer()

    def detach_viewer(self):
        """Rips the viewer out of the main app and puts it in a new window."""
        self.floating_viewer = FloatingViewerWindow(self)
        self.ui.viewer_widget.setParent(self.floating_viewer)
        self.floating_viewer.layout.addWidget(self.ui.viewer_widget)
        self.floating_viewer.show()
        
        self.ui.btn_detach.setText("⬐") 
        self.ui.btn_detach.setToolTip("Reattach Viewer")

        # ==========================================
        # 🔹 DYNAMIC LAYOUT: Stack Tree above Gallery
        # ==========================================
        if not hasattr(self, 'original_sidebar_width'):
            self.original_sidebar_width = self.ui.sidebar_widget.maximumWidth()
            
        self.ui.sidebar_widget.setMaximumWidth(16777215) 
        self.centralWidget().layout().removeWidget(self.ui.sidebar_widget)
        self.ui.sidebar_widget.setParent(self.ui.vertical_splitter)
        self.ui.vertical_splitter.insertWidget(0, self.ui.sidebar_widget)
        self.ui.vertical_splitter.setSizes([400, 400])
        
        # ==========================================
        # 🔹 AUTO-RESIZE GALLERY TO SMALL
        # ==========================================
        # Save whatever size the user was currently using
        self.previous_gallery_mode = self.ui.gallery_section.current_mode
        # Force the gallery into "small" mode for the compact bottom layout
        if hasattr(self.ui.gallery_section, 'set_size_mode'):
            self.ui.gallery_section.set_size_mode("small")

    def reattach_viewer(self):
        """Pulls the viewer back into the main app and restores the UI layout."""
        if self.floating_viewer:
            
            # ==========================================
            # 🔹 RESTORE LAYOUT: Put Tree back on the left
            # ==========================================
            # FIX: Insert it back into the horizontal_splitter, NOT the main layout!
            self.ui.horizontal_splitter.insertWidget(0, self.ui.sidebar_widget)
            
            if hasattr(self, 'original_sidebar_width'):
                self.ui.sidebar_widget.setMaximumWidth(self.original_sidebar_width)
            
            self.ui.vertical_splitter.insertWidget(0, self.ui.viewer_widget)
            self.ui.vertical_splitter.setSizes([600, 200])
            
            # ==========================================
            # 🔹 RESTORE GALLERY SIZE
            # ==========================================
            # Snap the gallery back to whatever size it was before detaching!
            if hasattr(self, 'previous_gallery_mode') and hasattr(self.ui.gallery_section, 'set_size_mode'):
                self.ui.gallery_section.set_size_mode(self.previous_gallery_mode)
            
            # ==========================================
            # Clean up the floating window
            self.floating_viewer.deleteLater()
            self.floating_viewer = None
            
            self.ui.btn_detach.setText("⧉")
            self.ui.btn_detach.setToolTip("Detach Viewer (Multi-Monitor)")

    def on_filter_changed(self, text):
        """Triggers when the user changes the Dropdown."""
        # 1. Instantly hide/show items currently on screen
        self.apply_gallery_filter()
        
        # 2. 🔹 If a database search is active, we MUST restart the search 
        # so the database offset resets and fetches a fresh, pure batch!
        if getattr(self, 'db_connection', None) and self.ui.search_bar.text().strip():
            self.process_search()

    def apply_gallery_filter(self, *args):
        """Hides or shows gallery items based on the active dropdown filter AND name search."""
        if not hasattr(self.ui.gallery_section, 'filter_combo'):
            return
            
        filter_type = self.ui.gallery_section.filter_combo.currentText()
        
        # Grab the text from our new search box
        name_query = ""
        if hasattr(self.ui.gallery_section, 'name_filter_input'):
            name_query = self.ui.gallery_section.name_filter_input.text().strip().lower()
            
        list_widget = self.ui.gallery_section.list_widget
        
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if not item: continue
            
            text = item.text()
            text_lower = text.lower()
            
            # 1. Check if it matches the Text Search (if any)
            matches_name = True
            if name_query:
                matches_name = name_query in text_lower
                
            # 2. Check if it matches the Type Dropdown
            matches_type = True
            if filter_type == "Images":
                matches_type = "🎬" not in text
            elif filter_type == "Videos":
                matches_type = "🖼️" not in text
                
            # 3. Only show the item if it passes BOTH tests!
            item.setHidden(not (matches_name and matches_type))

    def set_volume(self, value):
        volume_float = value / 100.0
        self.audio_output.setVolume(volume_float)
        
        if value == 0:
            self.ui.btn_volume.setIcon(self.get_icon("speaker-slash"))
            self.is_muted = True
        elif value < 33:
            self.ui.btn_volume.setIcon(self.get_icon("speaker-none"))
            self.is_muted = False
        elif value < 66:
            self.ui.btn_volume.setIcon(self.get_icon("speaker-low"))
            self.is_muted = False
        else:
            self.ui.btn_volume.setIcon(self.get_icon("speaker-high"))
            self.is_muted = False

    def toggle_mute(self):
        if self.is_muted:
            self.is_muted = False
            restore_val = self.previous_volume if self.previous_volume > 0 else 50
            self.ui.slider_volume.setValue(restore_val)
        else:
            self.is_muted = True
            self.previous_volume = self.ui.slider_volume.value()
            self.ui.slider_volume.setValue(0)

    def media_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.ui.video_container.btn_play.setIcon(self.get_icon("pause"))
            
            # 🔹 ONLY pause background workers if NOT on High Performance mode!
            if getattr(self, "current_perf_mode", "balanced") != "high":
                if hasattr(self, "thumb_worker"):
                    self.thumb_worker.pause()
                if hasattr(self, "vid_thumb_worker") and hasattr(self.vid_thumb_worker, "pause"):
                    self.vid_thumb_worker.pause()
        else:
            self.ui.video_container.btn_play.setIcon(self.get_icon("play"))
            
            # 🔹 Always RESUME background workers when video pauses or finishes
            if hasattr(self, "thumb_worker"):
                self.thumb_worker.resume()
            if hasattr(self, "vid_thumb_worker") and hasattr(self.vid_thumb_worker, "resume"):
                self.vid_thumb_worker.resume()

    # --- EXISTING PLAYER LOGIC METHODS ---
    def skip_backward(self):
        self.flash_button_icon(self.ui.btn_skip_backward, "back 10Sec")
        current_pos = self.media_player.position()
        self.media_player.setPosition(max(0, current_pos - 10000))

    def skip_forward(self):
        self.flash_button_icon(self.ui.btn_skip_forward, "skip 10Sec")
        current_pos = self.media_player.position()
        duration = self.media_player.duration()
        if duration > 0:
            self.media_player.setPosition(min(duration, current_pos + 10000))
   
   
    def play_previous(self):
        list_widget = self.ui.gallery_section.list_widget
        if list_widget.count() == 0: return

        current_row = list_widget.currentRow()
        new_row = max(0, current_row - 1) if current_row > 0 else 0

        if new_row != current_row:
            list_widget.setCurrentRow(new_row)
            item = list_widget.item(new_row)
            if item:
                list_widget.scrollToItem(item)
                path = item.data(Qt.ItemDataRole.UserRole)
                self.load_media(path) 

    def open_settings_dialog(self):
        """Opens the Settings dialog and handles database reconnection if it changes."""
        # Import the new dialog file
        from Src.Dialogs.settings_dialog import SettingsDialog
        import os
        import json
        
        # 🔹 Save config permanently in the user's AppData folder so it survives compilation!
        appdata_path = os.environ.get('APPDATA', os.path.expanduser('~'))
        config_path = os.path.join(appdata_path, 'MediaNest', 'config.json')
        
        # Launch the dialog
        dialog = SettingsDialog(config_path, self)
        
        # If the user clicks "Save" and the dialog closes successfully...
        if dialog.exec():
            # Only reconnect if they actually picked a new folder
            if dialog.db_folder_changed:
                if getattr(self, 'db_connection', None):
                    try:
                        self.db_connection.close()
                    except Exception:
                        pass
                
                self.connect_to_database(dialog.new_db_path)

    def show_gallery_context_menu(self, position):
        list_widget = self.ui.gallery_section.list_widget
        item = list_widget.itemAt(position)
        
        if item:
            # 🔹 Block signals so right-clicking DOES NOT auto-play the media!
            list_widget.blockSignals(True)
            list_widget.setCurrentItem(item)
            list_widget.blockSignals(False)
            
        selected_path = item.data(Qt.ItemDataRole.UserRole) if item else None
        target_folder = self.get_active_target_folder()
        
        global_pos = list_widget.viewport().mapToGlobal(position)
        self.file_ops.show_menu(global_pos, list_widget, selected_path, target_folder)

    def show_tree_context_menu(self, position):
        index = self.ui.tree_view.indexAt(position)
        
        if index.isValid():
            #  Block signals here too
            self.ui.tree_view.blockSignals(True)
            self.ui.tree_view.setCurrentIndex(index)
            self.ui.tree_view.blockSignals(False)
            
            item = self.get_source_item(index)
            selected_path = str(item.data(Qt.ItemDataRole.UserRole))
            is_folder = item.data(Qt.ItemDataRole.UserRole + 2)
            
            # : Tell the context menu this is a locked virtual folder
            if selected_path.startswith("VIRTUAL_"):
                target_folder = "VIRTUAL_BLOCK"
            else:
                target_folder = selected_path if is_folder else os.path.dirname(selected_path)
        else:
            selected_path = None
            target_folder = self.get_active_target_folder()
            
        global_pos = self.ui.tree_view.viewport().mapToGlobal(position)
        self.file_ops.show_menu(global_pos, self.ui.tree_view, selected_path, target_folder)

    def get_active_target_folder(self):
        """Determines where a paste operation should go based on UI focus."""
        # 🔹 Block paste if a Database Search is currently active
        if getattr(self, 'db_connection', None) and self.ui.search_bar.text().strip():
            return "VIRTUAL_BLOCK"

        if self.ui.tree_view.hasFocus():
            idx = self.ui.tree_view.currentIndex()
            if idx.isValid():
                item = self.get_source_item(idx)
                if item:
                    # Ensure path is a string to prevent errors
                    path = str(item.data(Qt.ItemDataRole.UserRole))
                    
                    # 🔹 Block paste if right-clicking a virtual search result
                    if path.startswith("VIRTUAL_"):
                        return "VIRTUAL_BLOCK"
                        
                    is_folder = item.data(Qt.ItemDataRole.UserRole + 2)
                    return path if is_folder else os.path.dirname(path)
                    
        return self.current_gallery_folder

    def get_focused_item_path(self):
        """Smartly grabs the selected path from EITHER the Tree OR the Gallery depending on focus."""
        if self.ui.tree_view.hasFocus():
            idx = self.ui.tree_view.currentIndex()
            if idx.isValid():
                item = self.get_source_item(idx)
                return item.data(Qt.ItemDataRole.UserRole) if item else None
                
        # Fallback to gallery if tree doesn't have focus
        item = self.ui.gallery_section.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def shortcut_copy(self):
        path = self.get_focused_item_path()
        if path:
            self.file_ops.on_copy(path)

    def shortcut_cut(self):
        path = self.get_focused_item_path()
        if path:
            self.file_ops.on_cut(path)

    def shortcut_paste(self):
        target = self.get_active_target_folder()
        
        # 🔹 Show a warning if they try to use Ctrl+V in search results
        if target == "VIRTUAL_BLOCK":
            QMessageBox.information(self, "Action Blocked", "You cannot paste files into a database search result.\n\nPlease clear the search or select a real folder first.")
            return
            
        if target:
            self.file_ops.on_paste(target)

    def shortcut_delete(self):
        path = self.get_focused_item_path()
        if path:
            self.file_ops.on_delete(path)

    def play_next(self):
        list_widget = self.ui.gallery_section.list_widget
        if list_widget.count() == 0: return

        current_row = list_widget.currentRow()
        if current_row == -1:
            new_row = 0
        else:
            new_row = min(list_widget.count() - 1, current_row + 1)

        if new_row != current_row:
            list_widget.setCurrentRow(new_row)
            item = list_widget.item(new_row)
            if item:
                list_widget.scrollToItem(item)
                path = item.data(Qt.ItemDataRole.UserRole)
                self.load_media(path)

    def toggle_play_pause(self):
        if (
            self.media_player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        ):
            self.media_player.pause()
        else:
            self.media_player.play()

    def toggle_fullscreen(self):
        # Block button signal to prevent double trigger
        self.ui.btn_fullscreen.blockSignals(True)

        if getattr(self, 'is_video_maximized', False):
            # POP IN: Restore to normal
            self.is_video_maximized = False
            self.ui.btn_fullscreen.setIcon(self.get_icon("fullscreen"))
            
            # Put the video container back into the app's layout
            self.ui.video_container.showNormal()
            self.ui.viewer_layout.addWidget(self.ui.video_container)
            
            self.autohide_timer.stop()
            self.ui.video_controls.show()
            self.ui.video_container.unsetCursor()
        else:
            # POP OUT: Detach and go true fullscreen
            self.is_video_maximized = True
            self.ui.btn_fullscreen.setIcon(self.get_icon("minimize"))
            
            # Detach from the main layout and make it a top-level window
            self.ui.video_container.setParent(None)
            
            # This will cover the taskbar instantly
            self.ui.video_container.showFullScreen()
            self.media_player.setPlaybackRate(1.0)
            
            self.autohide_timer.start()

        # Re-enable after short delay
        QTimer.singleShot(150, lambda: self.ui.btn_fullscreen.blockSignals(False))

    def _reset_fullscreen_flag(self):
        self._is_toggling_fullscreen = False

    def position_changed(self, position):
        self.ui.slider_progress.setValue(position)
        self.update_time_labels()

    def duration_changed(self, duration):
        self.ui.slider_progress.setRange(0, duration)
        self.update_time_labels()

    def set_position(self, position):
        self.media_player.setPosition(position)

    def update_time_labels(self):
        duration = self.media_player.duration()
        position = self.media_player.position()
        self.ui.lbl_current_time.setText(self.format_time(position))
        self.ui.lbl_total_time.setText(self.format_time(duration))

    def release_media_file(self, path):
        """Forces the app to completely drop OS-level file locks."""
        if not path:
            return

        target = os.path.normcase(os.path.abspath(path))

        dummy_file = os.path.abspath(
            os.path.join(self.asset_dir, "Logo.png")
        )
        dummy_url = QUrl.fromLocalFile(dummy_file)

        # -------------------------------------------------
        # 1. Release MAIN VIDEO PLAYER
        # -------------------------------------------------
        if hasattr(self, "media_player"):
            try:
                if self.media_player.source().isLocalFile():
                    current_vid = os.path.normcase(
                        os.path.abspath(
                            self.media_player.source().toLocalFile()
                        )
                    )

                    if current_vid == target:
                        self.media_player.stop()
                        self.media_player.setSource(QUrl())
                        self.ui.video_container.hide()
                        self.ui.lbl_placeholder.show()

                        QApplication.processEvents()
                        time.sleep(0.05)
            except Exception:
                pass

        # -------------------------------------------------
        # 2. Release VIDEO THUMBNAIL PLAYER
        # -------------------------------------------------
        if hasattr(self, "vid_thumb_worker"):
            try:
                self.vid_thumb_worker.timeout_timer.stop()

                self.vid_thumb_worker.player.stop()
                self.vid_thumb_worker.player.setSource(QUrl())

                self.vid_thumb_worker.is_processing = False
                self.vid_thumb_worker.current_path = None

                QApplication.processEvents()
            except Exception:
                pass

        # -------------------------------------------------
        # 3. Remove file from THUMBNAIL QUEUES
        # -------------------------------------------------
        if hasattr(self, "thumb_worker"):
            try:
                self.thumb_worker.queue = [
                    p for p in self.thumb_worker.queue
                    if os.path.normcase(os.path.abspath(p)) != target
                ]
            except Exception:
                pass

        if hasattr(self, "vid_thumb_worker"):
            try:
                self.vid_thumb_worker.queue = [
                    p for p in self.vid_thumb_worker.queue
                    if os.path.normcase(os.path.abspath(p)) != target
                ]
            except Exception:
                pass

        # -------------------------------------------------
        # 4. Release IMAGE VIEWER
        # -------------------------------------------------
        if getattr(self, "current_image_path", None):

            current_img = os.path.normcase(
                os.path.abspath(self.current_image_path)
            )

            if current_img == target:

                # Stop GIF if playing
                movie = self.ui.lbl_image.movie()
                if movie:
                    movie.stop()
                    self.ui.lbl_image.setMovie(None)
                    movie.deleteLater()

                # Release pixmap
                self.ui.lbl_image.clear()
                self.ui.lbl_image.setPixmap(QPixmap())

                self.current_image_path = None
                self.ui.image_view_container.hide()
                self.ui.lbl_placeholder.show()

                QApplication.processEvents()
                time.sleep(0.05)

        # -------------------------------------------------
        # 5. Clear IMAGE CACHE
        # -------------------------------------------------
        if hasattr(self, "image_cache"):
            try:
                keys_to_delete = [
                    k for k in self.image_cache
                    if os.path.normcase(os.path.abspath(k)) == target
                ]

                for k in keys_to_delete:
                    pix = self.image_cache.pop(k, None)
                    if pix:
                        del pix

                QApplication.processEvents()
                time.sleep(0.05)

            except Exception:
                pass

    def clear_media_viewer(self):
        """Safely stops any playing media and resets the preview area after a search."""
        # 1. Stop and hide the video player
        if hasattr(self, 'media_player'):
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            self.ui.video_container.hide()
            
            # 🔹 WAKE UP THE WORKERS: Resume thumbnails when media is cleared!
            if hasattr(self, "thumb_worker"):
                self.thumb_worker.resume()
            if hasattr(self, "vid_thumb_worker") and hasattr(self.vid_thumb_worker, "resume"):
                self.vid_thumb_worker.resume()
            
        # 2. Stop and hide the image viewer
        if getattr(self, "current_image_path", None):
            self.current_image_path = None
            movie = self.ui.lbl_image.movie()
            if movie:
                movie.stop()
                self.ui.lbl_image.setMovie(None)
            self.ui.image_view_container.hide()
            self.ui.manhwa_reader.hide()
            if hasattr(self.ui, 'manga_reader'):
                self.ui.manga_reader.hide()
            
        # 3. Bring back the default placeholder
        self.ui.lbl_placeholder.setText("Select a file to view")
        self.ui.lbl_placeholder.show()

    def format_time(self, ms):
        s = round(ms / 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02}:{m:02}:{s:02}"
        return f"{m:02}:{s:02}"

    # --- FILE & FOLDER LOGIC ---
    def open_folder_dialog(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder_path:
            self.load_root_folder(folder_path)

    def load_root_folder(self, path):
        if not path:
            return

        # If model is empty, set header
        if self.model.rowCount() == 0:
            self.model.setHorizontalHeaderLabels(["Name"])

        root_name = os.path.basename(path)

        # Prevent duplicate roots
        for row in range(self.model.rowCount()):
            existing_item = self.model.item(row)
            if existing_item.data(Qt.ItemDataRole.UserRole) == path:
                return  # Already added

        # Create new root item
        root_item = self.create_folder_item(root_name, path)
        self.model.appendRow(root_item)

        # Populate normally
        self.populate_normal(root_item, path)

        # Expand the newly added root
        proxy_index = self.proxy_model.mapFromSource(root_item.index())
        self.ui.tree_view.expand(proxy_index)

    def create_folder_item(self, name, path):
        item = QStandardItem(f"{name}")
        item.setData(path, Qt.ItemDataRole.UserRole)
        item.setData(True, Qt.ItemDataRole.UserRole + 2)
        item.setData(False, Qt.ItemDataRole.UserRole + 4)
        item.setData(False, Qt.ItemDataRole.UserRole + 5)
        has_any, has_sub = self.analyze_folder_content(path)
        item.setData(has_any, Qt.ItemDataRole.UserRole + 3)
        item.setData(has_sub, Qt.ItemDataRole.UserRole + 6)
        item.setData(False, Qt.ItemDataRole.UserRole + 30)
        item.setIcon(QIcon(os.path.join("assets", "uisvg", "folder.svg")))
        if has_any: item.appendRow(QStandardItem("Loading..."))
        return item

    def create_file_item(self, name, path, is_video):
        item = QStandardItem(name)
        item.setData(path, Qt.ItemDataRole.UserRole)
        item.setData(False, Qt.ItemDataRole.UserRole + 2)
        svg_name = "video.svg" if is_video else "image.svg"
        item.setIcon(QIcon(os.path.join("assets", "uisvg", svg_name)))
        return item

    def analyze_folder_content(self, path):
        has_any = False; has_subs = False
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_dir(): return True, True
                    if not has_any and entry.is_file():
                        name = entry.name.lower()
                        if any(name.endswith(e) for e in self.clean_img_exts + self.clean_vid_exts):
                            has_any = True
        except: pass
        return has_any, has_subs

    def get_source_item(self, index):
        if hasattr(self, 'proxy_model') and index.model() == self.proxy_model:
            source_index = self.proxy_model.mapToSource(index)
            return self.model.itemFromIndex(source_index)
        return self.model.itemFromIndex(index)    

    def on_item_expanded(self, index):
        item = self.get_source_item(index)
        
        if not item: 
            return
            
        if item.data(Qt.ItemDataRole.UserRole + 5) or item.data(Qt.ItemDataRole.UserRole + 4): 
            return
            
        path = str(item.data(Qt.ItemDataRole.UserRole))
        
        # 🔹 VIRTUAL FOLDER FIX
        if path.startswith("VIRTUAL_"):
            return
            
        if os.path.isdir(path):
            self.populate_normal(item, path)
        else:
            item.setData(True, Qt.ItemDataRole.UserRole + 5)

    def eventFilter(self, obj, event):
        try:
            # 1. Catch Escape key globally when in fullscreen
            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                if getattr(self, 'is_video_maximized', False):
                    self.toggle_fullscreen()
                    return True

            # 🔹 Catch Clipboard Shortcuts Globally before the gallery steals them!
            if event.type() == QEvent.Type.KeyPress:
                # Don't intercept if the user is typing in the Search Bar
                if obj.__class__.__name__ != "QLineEdit":
                    if event.matches(QKeySequence.StandardKey.Copy):
                        self.shortcut_copy()
                        return True
                    elif event.matches(QKeySequence.StandardKey.Cut):
                        self.shortcut_cut()
                        return True
                    elif event.matches(QKeySequence.StandardKey.Paste):
                        self.shortcut_paste()
                        return True
                    elif event.key() == Qt.Key.Key_Delete:
                        self.shortcut_delete()
                        return True

            # 2. Catch double-click on the video to toggle fullscreen
            if event.type() == QEvent.Type.MouseButtonDblClick:
                if obj == self.ui.video_widget:
                    self.toggle_fullscreen()
                    return True

            # 3. Handle mouse movement to auto-show controls
            if event.type() in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress):
                if getattr(self, 'is_video_maximized', False):
                    self.show_fullscreen_controls()
                    
            return super().eventFilter(obj, event)
            
        except RuntimeError:
            # The C++ object was already destroyed by Qt before Python could process this event.
            # Safely ignore it to prevent the app from crashing.
            return False

    def hide_fullscreen_controls(self):
        if getattr(self, 'is_video_maximized', False):
            self.ui.video_controls.hide()
            # Hide cursor on the new detached window
            self.ui.video_container.setCursor(Qt.CursorShape.BlankCursor) 

    def show_fullscreen_controls(self):
        if getattr(self, 'is_video_maximized', False):
            if self.ui.video_controls.isHidden():
                self.ui.video_controls.show()
                # Show cursor on the detached window
                self.ui.video_container.unsetCursor() 
            self.autohide_timer.start()

    def populate_normal(self, parent_item, folder_path):
        parent_item.removeRows(0, parent_item.rowCount())
        try:
            entries = sorted(os.scandir(folder_path), key=lambda e: (not e.is_dir(), e.name.lower()))
            for entry in entries:
                if entry.is_dir():
                    parent_item.appendRow(self.create_folder_item(entry.name, entry.path))
                elif entry.is_file():
                    name = entry.name.lower()
                    is_img = any(name.endswith(e) for e in self.clean_img_exts)
                    is_vid = any(name.endswith(e) for e in self.clean_vid_exts)
                    if is_img or is_vid:
                        parent_item.appendRow(self.create_file_item(entry.name, entry.path, is_vid))
        except PermissionError: pass
        parent_item.setData(True, Qt.ItemDataRole.UserRole + 5)

    def start_flattening(self, parent_item, folder_path):
        parent_item.removeRows(0, parent_item.rowCount())
        loading = QStandardItem("⏳ Scanning...")
        parent_item.appendRow(loading)
        
        self.ui.gallery_section.list_widget.clear()
        self.thumbnail_map.clear()
        self.thumb_worker.clear_queue()
        self.vid_thumb_worker.clear_queue()
        self.thumb_worker.resume()
        
        if self.scanner_thread and self.scanner_thread.isRunning():
            self.scanner_thread.stop()
            self.scanner_thread.wait()

        self.loading_item_ref = parent_item
        self.scanner_thread = ScannerWorker(folder_path, self.clean_img_exts, self.clean_vid_exts)
        self.scanner_thread.batch_found.connect(self.on_batch_received)
        self.scanner_thread.finished.connect(self.on_scan_finished)
        self.scanner_thread.start()

    def on_batch_received(self, folder_path, batch):
        parent_item = self.loading_item_ref

        # 🔒 Safety check — ignore if folder no longer active
        if not parent_item:
            return

        # Ignore results if they belong to a different folder
        if parent_item.data(Qt.ItemDataRole.UserRole) != folder_path:
            return

        # Remove loading indicator if present
        if parent_item.rowCount() == 1 and parent_item.child(0).text() == "⏳ Scanning...":
            parent_item.removeRow(0)

        # Add items to tree
        for display_name, full_path, is_vid in batch:
            parent_item.appendRow(self.create_file_item(display_name, full_path, is_vid))

        # Prepare thumbnails
        files_for_img_thumbs = []
        files_for_vid_thumbs = []

        for display_name, full_path, is_vid in batch:
            clean_name = os.path.basename(display_name)

            item = QListWidgetItem(clean_name)
            item.setData(Qt.ItemDataRole.UserRole, full_path)
            item.setSizeHint(QSize(240, 260))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)

            icon_text = "⏳"
            item.setText(f"{icon_text} {clean_name}")

            if is_vid:
                files_for_vid_thumbs.append(full_path)
            else:
                files_for_img_thumbs.append(full_path)

            self.thumbnail_map[full_path] = item
            self.ui.gallery_section.list_widget.addItem(item)

        if files_for_img_thumbs:
            self.thumb_worker.add_to_queue(files_for_img_thumbs)

        if files_for_vid_thumbs:
            self.vid_thumb_worker.add_to_queue(files_for_vid_thumbs)

    def on_thumbnail_ready(self, path, qimage):
        # 🔹 Put the image in the basket. DO NOT touch the UI yet!
        self.pending_thumbnails[path] = qimage

    def apply_pending_thumbnails(self):
        """Paints all waiting thumbnails smoothly without freezing the entire widget."""
        if not self.pending_thumbnails:
            return

        # 🔹 REMOVED setUpdatesEnabled(False) so it doesn't cause a strobe effect!

        # Loop through everything in our basket
        for path, qimage in list(self.pending_thumbnails.items()):
            if path in self.thumbnail_map:
                try:
                    item = self.thumbnail_map[path]
                    if self.ui.gallery_section.list_widget.row(item) != -1:
                        pixmap = QPixmap.fromImage(qimage)
                        item.setIcon(QIcon(pixmap))
                        
                        is_gallery = item.data(Qt.ItemDataRole.UserRole + 1) == "gallery"
                        if is_gallery:
                            icon_text = ""
                        else:
                            icon_text = ""
                        
                        # Only update the text if it still has the hourglass to prevent micro-stutters
                        if "⏳" in item.text():
                            clean_name = os.path.basename(path)
                            item.setText(clean_name)
                except RuntimeError:
                    pass

        # Empty the basket for the next round
        self.pending_thumbnails.clear()

    def on_scan_finished(self):
        if not self.loading_item_ref:
            return

        # Safety: if folder is no longer flattened, ignore
        if not self.loading_item_ref.data(Qt.ItemDataRole.UserRole + 4):
            self.loading_item_ref = None
            return

        self.loading_item_ref.setData(True, Qt.ItemDataRole.UserRole + 5)

        if (
            self.loading_item_ref.rowCount() == 1
            and self.loading_item_ref.child(0).text() == "⏳ Scanning..."
        ):
            self.loading_item_ref.removeRow(0)
            self.loading_item_ref.appendRow(QStandardItem("No media found."))

        self.loading_item_ref = None
        
    def on_folder_toggle(self, index):
        item = self.get_source_item(index)
        if not item:
            return

        # Ensure path is cast to string to safely use .startswith()
        path = str(item.data(Qt.ItemDataRole.UserRole))
        is_currently_flat = item.data(Qt.ItemDataRole.UserRole + 4)

        # Toggle open state
        is_open = item.data(Qt.ItemDataRole.UserRole + 30)
        item.setData(not is_open, Qt.ItemDataRole.UserRole + 30)

        # 🔹 VIRTUAL FOLDER FIX: Don't try to read fake folders from the hard drive!
        if path.startswith("VIRTUAL_"):
            if is_open:
                self.ui.tree_view.expand(index)
            else:
                self.ui.tree_view.collapse(index)
            self.ui.tree_view.viewport().update()
            return

        # --- Your existing flatten logic ---
        if is_currently_flat:
            if self.scanner_thread and self.scanner_thread.isRunning():
                self.scanner_thread.stop()

            self.thumb_worker.clear_queue()
            self.vid_thumb_worker.clear_queue()

            item.setData(False, Qt.ItemDataRole.UserRole + 4)
            self.populate_normal(item, path)
            self.update_gallery_from_path(path)
        else:
            item.setData(True, Qt.ItemDataRole.UserRole + 4)
            self.start_flattening(item, path)

        self.ui.tree_view.expand(index)
        self.ui.tree_view.viewport().update()

    def on_tree_item_clicked(self, index):
        item = self.get_source_item(index)
        if not item: return
        path = str(item.data(Qt.ItemDataRole.UserRole))
        is_folder = item.data(Qt.ItemDataRole.UserRole + 2)
        is_flattened = item.data(Qt.ItemDataRole.UserRole + 4)

        if is_folder:
            if not self.ui.tree_view.isExpanded(index): self.ui.tree_view.expand(index)
            
            # 🔹 VIRTUAL FOLDER FIX
            if path.startswith("VIRTUAL_"):
                return
                
            if not is_flattened: self.update_gallery_from_path(path)
        else:
            self.load_media(path)
            parent = item.parent()
            if parent and not parent.data(Qt.ItemDataRole.UserRole + 4):
                 parent_path = str(parent.data(Qt.ItemDataRole.UserRole))
                 
                 # 🔹 VIRTUAL FOLDER FIX
                 if not parent_path.startswith("VIRTUAL_"):
                     self.update_gallery_from_path(parent_path)

    def update_gallery_from_path(self, folder_path, force=False):
        if not force and self.current_gallery_folder == folder_path: return 
        self.current_gallery_folder = folder_path
        
        self.ui.gallery_section.list_widget.clear()
        self.thumbnail_map.clear()
        self.thumb_worker.clear_queue()
        self.vid_thumb_worker.clear_queue()
        self.thumb_worker.resume()
        
        files_for_img_thumbs = []
        files_for_vid_thumbs = []
        
        try:
            entries = sorted(os.scandir(folder_path), key=lambda e: e.name.lower())
            for entry in entries:
                if entry.is_file():
                    name = entry.name.lower()
                    is_img = any(name.endswith(e) for e in self.clean_img_exts)
                    is_vid = any(name.endswith(e) for e in self.clean_vid_exts)
                    if is_img or is_vid:
                        item = QListWidgetItem(entry.name)
                        item.setData(Qt.ItemDataRole.UserRole, entry.path)
                        item.setSizeHint(QSize(240, 260))
                        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
                        
                        icon_text = "⏳"
                        item.setText(f"{icon_text} {entry.name}")
                        
                        if is_vid:
                            files_for_vid_thumbs.append(entry.path)
                        else:
                            files_for_img_thumbs.append(entry.path)
                            
                        self.thumbnail_map[entry.path] = item
                        self.ui.gallery_section.list_widget.addItem(item)
        except: pass
        
        if files_for_img_thumbs: self.thumb_worker.add_to_queue(files_for_img_thumbs)
        if files_for_vid_thumbs: self.vid_thumb_worker.add_to_queue(files_for_vid_thumbs)

    def refresh_folder_ui(self, folder_path):
        """Forces a real-time UI refresh of both the Gallery and Tree View for a specific folder."""
        if not folder_path or not os.path.exists(folder_path):
            return

        # 1. Force refresh the Gallery if the user is currently looking at this folder
        if self.current_gallery_folder == folder_path:
            self.update_gallery_from_path(folder_path, force=True)

        # 2. Find the folder in the Tree View and force it to rescan its files
        def search_and_refresh(parent_item):
            for i in range(parent_item.rowCount()):
                child = parent_item.child(i)
                if not child: continue
                
                # If we found the folder that was modified
                if child.data(Qt.ItemDataRole.UserRole) == folder_path:
                    # Refresh it based on whether it is flattened or normal
                    if child.data(Qt.ItemDataRole.UserRole + 4): 
                        self.start_flattening(child, folder_path)
                    else:
                        self.populate_normal(child, folder_path)
                    return True
                
                # If it's a folder, search inside it recursively
                if child.data(Qt.ItemDataRole.UserRole + 2):
                    if search_and_refresh(child):
                        return True
            return False

        search_and_refresh(self.model.invisibleRootItem())

    def load_media(self, path):
        if not path: return
        
        # 🔹 If they clicked a new file, cancel the clear timer so it doesn't kill their new media!
        if hasattr(self, 'clear_player_timer') and self.clear_player_timer.isActive():
            self.clear_player_timer.stop()
            
        name = path.lower()
        is_gallery = os.path.isdir(path)
        is_image = any(name.endswith(ext) for ext in self.clean_img_exts)
        is_video = any(name.endswith(ext) for ext in self.clean_vid_exts)
        
        if is_gallery:
            self.current_image_path = None
            self.show_gallery(path)
        elif is_image:
            self.current_image_path = path
            self.show_image(path)
        elif is_video:
            self.current_image_path = None
            self.play_video(path)

    def show_gallery(self, path):
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.ui.video_container.hide() 
        self.ui.lbl_placeholder.hide()
        
        if hasattr(self, "thumb_worker"):
            self.thumb_worker.resume()
        if hasattr(self, "vid_thumb_worker") and hasattr(self.vid_thumb_worker, "resume"):
            self.vid_thumb_worker.resume()
            
        self.ui.image_view_container.show()
        
        movie = self.ui.lbl_image.movie()
        if movie:
            movie.stop()
            self.ui.lbl_image.setMovie(None)
            movie.deleteLater()
            
        self.ui.lbl_image.hide()
        self.ui.manhwa_reader.hide()
        self.ui.manhwa_zoom_slider.hide()
        
        if hasattr(self.ui, 'manga_reader'):
            self.ui.manga_reader.show()
            self.ui.manga_reader.load_folder(path)

    def show_image(self, path):
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.ui.video_container.hide() 
        self.ui.lbl_placeholder.hide()
        
        # 🔹 WAKE UP THE WORKERS: Unpause thumbnails when switching away from a video!
        if hasattr(self, "thumb_worker"):
            self.thumb_worker.resume()
        if hasattr(self, "vid_thumb_worker") and hasattr(self.vid_thumb_worker, "resume"):
            self.vid_thumb_worker.resume()
        
        # 🔹 VITAL: Show the container holding BOTH the scroll area and the slider
        self.ui.image_view_container.show()

        # 🔹 Clear any playing GIF before loading a new image
        movie = self.ui.lbl_image.movie()
        if movie:
            movie.stop()
            self.ui.lbl_image.setMovie(None)
            movie.deleteLater()

        if hasattr(self.ui, 'manga_reader'):
            self.ui.manga_reader.hide()

        # ==========================================
        # 1. 🔹 Handle Animated GIFs (Standard UI)
        # ==========================================
        if path.lower().endswith('.gif'):
            self.ui.manhwa_reader.hide()
            self.ui.lbl_image.show()
            self.ui.manhwa_zoom_slider.hide()
            
            with open(path, 'rb') as f:
                self.current_gif_data = QByteArray(f.read())
                
            self.gif_buffer = QBuffer(self.current_gif_data)
            self.gif_buffer.open(QBuffer.OpenModeFlag.ReadOnly)
            
            movie = QMovie()
            movie.setDevice(self.gif_buffer)
            
            # The custom DynamicImageLabel will scale the movie automatically!
            self.ui.lbl_image.setMovie(movie)
            movie.start()
            if hasattr(self.ui.lbl_image, "_scale_content"):
                self.ui.lbl_image._scale_content()
            return

        # ==========================================
        # 🔹 SMART ROUTER: Normal Photo vs Manhwa
        # ==========================================
        # Instantly peek at the image header to get dimensions without loading pixels into RAM
        reader = QImageReader(path)
        orig_size = reader.size()
        aspect_ratio = orig_size.height() / max(orig_size.width(), 1) if orig_size.isValid() else 1.0

        # 2. 🔹 Handle Manhwa (Virtual Reader UI)
        if aspect_ratio > 2.5:
            self.ui.lbl_image.hide()
            self.ui.manhwa_reader.show()
            # --- BRING BACK THE ZOOM SLIDER ---
            self.ui.manhwa_zoom_slider.blockSignals(True)
            self.ui.manhwa_zoom_slider.setValue(100)
            self.ui.manhwa_zoom_slider.blockSignals(False)
            self.ui.manhwa_zoom_slider.show()

            try: 
                self.ui.manhwa_zoom_slider.valueChanged.disconnect()
            except TypeError: 
                pass 
            self.ui.manhwa_zoom_slider.valueChanged.connect(self.zoom_virtual_manhwa)
            # ----------------------------------

            folder_path = os.path.dirname(path)
            self.ui.manhwa_reader.load_folder(folder_path, jump_to_path=path)

        # 3. 🔹 Handle Normal Photos (Standard UI)
        else:
            self.ui.manhwa_reader.hide()
            self.ui.lbl_image.show()
            self.ui.manhwa_zoom_slider.hide()

            MAX_CACHE = 50
            if path in self.image_cache:
                pixmap = self.image_cache[path]
            else:
                try:
                    # Load into RAM safely to prevent OS locking
                    with open(path, 'rb') as f:
                        data = f.read()
                    
                    image = QImage()
                    image.loadFromData(data)
                    pixmap = QPixmap.fromImage(image)
                except Exception:
                    pixmap = QPixmap()

                if not pixmap.isNull():
                    self.image_cache[path] = pixmap
                
                    if len(self.image_cache) > MAX_CACHE:
                        self.image_cache.pop(next(iter(self.image_cache)))

            # Pass the RAW pixmap to our smart label and it will instantly resize it!
            if not pixmap.isNull():
                if hasattr(self.ui.lbl_image, "set_raw_pixmap"):
                    self.ui.lbl_image.set_raw_pixmap(pixmap)
                else:
                    self.ui.lbl_image.setPixmap(pixmap)

    def zoom_virtual_manhwa(self, percentage):
        """Passes the slider zoom percentage into the high-performance reader."""
        if hasattr(self.ui, 'manhwa_reader'):
            self.ui.manhwa_reader.set_zoom(percentage)

    # ==========================================
    # 🔹 MANHWA ZOOM ENGINE
    # ==========================================
    def zoom_manhwa(self, zoom_percentage):
        """Dynamically rescales the Manhwa image based on the slider percentage."""
        if not getattr(self, 'current_manhwa_pixmap', None):
            return

        # Calculate the new target width (e.g., 150% of the screen width)
        new_width = int(self.manhwa_base_width * (zoom_percentage / 100.0))

        # IMPORTANT: Always scale from the ORIGINAL high-res image so it never loses quality!
        scaled_pixmap = self.current_manhwa_pixmap.scaledToWidth(new_width, Qt.TransformationMode.SmoothTransformation)
        self.ui.lbl_image.setPixmap(scaled_pixmap)

    def play_video(self, path):
        if not path:
            return

        if getattr(self, "current_perf_mode", "balanced") != "high":
            if hasattr(self, "thumb_worker"):
                self.thumb_worker.pause()
            if hasattr(self, "vid_thumb_worker"):
                try:
                    self.vid_thumb_worker.pause()
                except AttributeError:
                    pass

        # 🔹 Hide the ENTIRE image viewer container (fixes the broken scrollbar overlap!)
        self.ui.image_view_container.hide()
        self.ui.lbl_placeholder.hide()

        # 🔹 Show video container
        self.ui.video_container.show()

        # 🔹 Stop any currently playing media
        self.media_player.stop()

        # 🔹 Load new video
        self.media_player.setSource(QUrl.fromLocalFile(path))

        # 🔹 Ensure stable playback speed
        self.media_player.setPlaybackRate(1.0)

        # 🔹 Start playback
        self.media_player.play()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            # Always navigate the gallery by default
            self.play_previous()
            event.accept()
            return

        elif event.key() == Qt.Key.Key_Right:
            # Always navigate the gallery by default
            self.play_next()
            event.accept()
            return

        elif event.key() == Qt.Key.Key_Space:
            # Only toggle play/pause if a video is actually on screen
            if self.ui.video_container.isVisible():
                self.toggle_play_pause()
            event.accept()
            return

        super().keyPressEvent(event)

    def on_gallery_item_changed(self, current_item, previous_item):
        if current_item:
            path = current_item.data(Qt.ItemDataRole.UserRole)
            self.load_media(path)                

    def on_search_bar_typed(self, text):
        # Instead of searching immediately, start/reset the 300ms timer
        self.search_timer.start()

    def force_instant_search(self):
        # If the user hits "Enter", cancel the timer and search instantly
        self.search_timer.stop()
        self.process_search()

    def on_gallery_scroll(self, value):
        # Only trigger if we are searching a database
        if not getattr(self, 'db_connection', None):
            return
            
        search_text = self.ui.search_bar.text().strip().lower()
        if not search_text:
            return

        scrollbar = self.ui.gallery_section.list_widget.verticalScrollBar()
        
        # Safely check if we are already fetching
        if getattr(self, 'is_fetching_data', False):
            return
            
        # If the user scrolls within 100 pixels of the bottom, load the next chunk!
        if value >= scrollbar.maximum() - 100:
            self.is_fetching_data = True
            
            self.ui.lbl_placeholder.setText("⏳ Loading more...")
            self.ui.lbl_placeholder.show()
            filter_type = self.ui.gallery_section.filter_combo.currentText() if hasattr(self.ui.gallery_section, 'filter_combo') else "All"
            
            # 🔹 PERFORMANCE: Dynamic Scroll Batch Limits
            perf_mode = getattr(self, "current_perf_mode", "balanced")
            if perf_mode == "high":
                scroll_limit = 200
            elif perf_mode == "low":
                scroll_limit = 50
            else:
                scroll_limit = 100

            self.db_search_worker = DatabaseSearchWorker(
                self.current_db_path, 
                search_text, 
                limit=scroll_limit, 
                offset=self.current_search_offset, 
                search_id=self.current_search_id,
                filter_type=filter_type
            )
            self.db_search_worker.search_finished.connect(self.on_db_search_finished)
            self.db_search_worker.start()
            
            # Increase offset AFTER launching the worker so the NEXT scroll fetches the correct batch
            self.current_search_offset += scroll_limit

    def process_search(self):
        text = self.ui.search_bar.text()
        search_text = text.strip().lower()
        
        # 🔹 Start the 2-second countdown to clear the player!
        self.clear_player_timer.start(200) 

        if getattr(self, 'db_connection', None) and hasattr(self, 'current_db_path'):
            
            # 🔹 ANTI-BLINK FIX: Only show "Searching..." if the screen is already empty!
            if not self.ui.video_container.isVisible() and not self.ui.image_view_container.isVisible():
                self.ui.lbl_placeholder.setText("⏳ Searching...")
                self.ui.lbl_placeholder.show()

            if getattr(self, 'db_search_worker', None) and self.db_search_worker.isRunning():
                self.db_search_worker.stop()
                
                # ==========================================
                # 🔹 ANTI-FREEZE FIX: NO MORE .wait()
                # ==========================================
                # We orphan the old thread so it doesn't freeze the UI while SQL finishes.
                if not hasattr(self, 'zombie_workers'):
                    self.zombie_workers = []
                
                old_worker = self.db_search_worker
                self.zombie_workers.append(old_worker)
                
                # Let it die quietly and remove itself from RAM when finished
                old_worker.finished.connect(
                    lambda w=old_worker: self.zombie_workers.remove(w) if w in getattr(self, 'zombie_workers', []) else None
                )
                # ==========================================

            # --- START FRESH ---
            self.current_search_id += 1  # Invalidate any old background loops!
            
            filter_type = self.ui.gallery_section.filter_combo.currentText() if hasattr(self.ui.gallery_section, 'filter_combo') else "All"

            # 🔹 PERFORMANCE: Dynamic Initial Load Limits
            perf_mode = getattr(self, "current_perf_mode", "balanced")
            if perf_mode == "high":
                initial_limit = 1000
            elif perf_mode == "low":
                initial_limit = 100
            else:
                initial_limit = 300
                
            # 🔹  Set the offset to exactly where the next batch should START
            self.current_search_offset = initial_limit 

            # Blast the initial images instantly
            self.db_search_worker = DatabaseSearchWorker(
                self.current_db_path, 
                search_text, 
                limit=initial_limit, 
                offset=0, 
                search_id=self.current_search_id,
                filter_type=filter_type
            )
            self.db_search_worker.search_finished.connect(self.on_db_search_finished)
            self.db_search_worker.start()
            return 
            
        self.proxy_model.set_search_text(search_text)


    def on_db_search_finished(self, results, folders_map, search_text, is_appending, search_id):
        # 1. GHOST PROTECTION: If the user typed something new, discard this data!
        if search_id != self.current_search_id:
            return 

        self.ui.lbl_placeholder.hide()

        if not results and not search_text:
            for row in range(self.model.rowCount()):
                item = self.model.item(row)
                if item and item.text().startswith("Database Results"):
                    self.model.removeRow(row)
                    break
            if self.current_gallery_folder:
                self.update_gallery_from_path(self.current_gallery_folder, force=True)
            else:
                self.ui.gallery_section.list_widget.clear()
            return

        # Clear UI ONLY if this is the very first batch (offset 0)
        if not is_appending:
            self.ui.gallery_section.list_widget.clear()
            self.thumbnail_map.clear()
            self.thumb_worker.clear_queue()
            self.vid_thumb_worker.clear_queue()
            self.thumb_worker.resume()

        # Virtual Tree Setup
        search_root = None
        for row in range(self.model.rowCount()):
            item = self.model.item(row)
            if item and item.text().startswith("Database Results"):
                search_root = item
                break
                
        if not is_appending:
            if search_root:
                search_root.removeRows(0, search_root.rowCount()) 
                search_root.setText(f"Database Results: {search_text}")
            else:
                search_root = QStandardItem(f"Database Results: {search_text}")
                search_root.setData("VIRTUAL_ROOT", Qt.ItemDataRole.UserRole)
                search_root.setData(True, Qt.ItemDataRole.UserRole + 2) 
                search_root.setData(True, Qt.ItemDataRole.UserRole + 4) 
                self.model.insertRow(0, search_root) 
                
            from PyQt6.QtGui import QIcon
            import os
            search_root.setIcon(QIcon(os.path.join("assets", "uisvg", "search.svg")))

        files_for_img_thumbs = []
        files_for_vid_thumbs = []

        # 🔹 SAVE SCROLL POSITION & SELECTION 🔹
        scrollbar = self.ui.gallery_section.list_widget.verticalScrollBar()
        saved_scroll_pos = scrollbar.value()
        saved_row = self.ui.gallery_section.list_widget.currentRow()

        # 🔹 FREEZE THE UI: Stop redrawing the screen until all items are loaded
        self.ui.gallery_section.list_widget.setUpdatesEnabled(False)

        # Append the new chunk to the Gallery
        for file_path, file_name, media_type in results:
            is_vid = media_type == "video" or (media_type == "image" and any(file_name.lower().endswith(e) for e in self.clean_vid_exts))
            is_gallery = media_type == "gallery"
            
            item = QListWidgetItem(file_name)
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            if is_gallery:
                item.setData(Qt.ItemDataRole.UserRole + 1, "gallery")
                
            item.setSizeHint(QSize(240, 260))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            
            if is_gallery:
                icon_text = "⏳"
            else:
                icon_text = "⏳"
                
            item.setText(f"{icon_text} {file_name}")
            
            if is_vid: files_for_vid_thumbs.append(file_path)
            else: files_for_img_thumbs.append(file_path)
                
            self.thumbnail_map[file_path] = item
            self.ui.gallery_section.list_widget.addItem(item)

        # 🔹 UNFREEZE THE UI: Draw them all at exactly the same time!
        self.ui.gallery_section.list_widget.setUpdatesEnabled(True)
        
        # 🔹 RESTORE SCROLL POSITION & SELECTION 🔹
        if is_appending:
            scrollbar.setValue(saved_scroll_pos)
            
            if saved_row >= 0:
                # Silently re-highlight the exact image we were on
                self.ui.gallery_section.list_widget.setCurrentRow(saved_row)
                
            # 🔹 BUG FIX: Force the keyboard to stay connected to the gallery!
            self.ui.gallery_section.list_widget.setFocus()

        # Append to the Tree View
        for folder_name, files in folders_map.items():
            existing_folder = None
            if search_root:
                for i in range(search_root.rowCount()):
                    if search_root.child(i).data(Qt.ItemDataRole.UserRole) == f"VIRTUAL_GROUP_{folder_name}":
                        existing_folder = search_root.child(i)
                        break
            
            if not existing_folder:
                existing_folder = QStandardItem(folder_name)
                from PyQt6.QtGui import QIcon
                import os
                existing_folder.setIcon(QIcon(os.path.join("assets", "uisvg", "folder.svg")))
                existing_folder.setData(f"VIRTUAL_GROUP_{folder_name}", Qt.ItemDataRole.UserRole)
                existing_folder.setData(True, Qt.ItemDataRole.UserRole + 2) 
                existing_folder.setData(True, Qt.ItemDataRole.UserRole + 4) 
                search_root.appendRow(existing_folder)
            
            for f_path, f_name, media_type in files:
                is_vid = media_type == "video" or (media_type == "image" and any(f_name.lower().endswith(e) for e in self.clean_vid_exts))
                file_item = self.create_file_item(f_name, f_path, is_vid)
                existing_folder.appendRow(file_item)

            existing_folder.setText(f"{folder_name} ({existing_folder.rowCount()} items)")

        if not is_appending and search_root:
            proxy_index = self.proxy_model.mapFromSource(search_root.index())
            self.ui.tree_view.expand(proxy_index)

        if files_for_img_thumbs: self.thumb_worker.add_to_queue(files_for_img_thumbs)
        if files_for_vid_thumbs: self.vid_thumb_worker.add_to_queue(files_for_vid_thumbs)

        # 🔹 UNLOCK THE SCROLLBAR: Let the user load more only when they scroll!
        self.is_fetching_data = False

    def render_search_batch(self):
        # Abort if the user typed something new while we were rendering
        if getattr(self, 'cancel_search_rendering', False):
            return 
            
        items_to_render = 100 # Adjust this if you want faster/slower batches
        rendered = 0
        
        files_for_img_thumbs = []
        files_for_vid_thumbs = []
        
        # 1. Render a chunk of Gallery Items
        self.ui.gallery_section.list_widget.setUpdatesEnabled(False) # 🔹 FREEZE UI

        while self.search_render_results and rendered < items_to_render:
            file_path, file_name, media_type = self.search_render_results.pop(0)
            is_vid = media_type == "video" or (media_type == "image" and any(file_name.lower().endswith(e) for e in self.clean_vid_exts))
            is_gallery = media_type == "gallery"
            
            item = QListWidgetItem(file_name)
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            if is_gallery:
                item.setData(Qt.ItemDataRole.UserRole + 1, "gallery")
                
            item.setSizeHint(QSize(240, 260))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            
            if is_gallery:
                icon_text = "⏳"
            else:
                icon_text = "⏳"
                
            item.setText(f"{icon_text} {file_name}")
            
            if is_vid: files_for_vid_thumbs.append(file_path)
            else: files_for_img_thumbs.append(file_path)
                
            self.thumbnail_map[file_path] = item
            self.ui.gallery_section.list_widget.addItem(item)
            rendered += 1
            
        self.ui.gallery_section.list_widget.setUpdatesEnabled(True) # 🔹 UNFREEZE UI

        # 2. Render a chunk of Tree Folders
        # We render 1 whole folder per batch to prevent weird split-folder rendering issues
        if self.search_render_folders and rendered < items_to_render:
            folder_name, files = self.search_render_folders.pop(0)
            folder_item = QStandardItem(f"{folder_name} ({len(files)} items)")
            from PyQt6.QtGui import QIcon
            import os
            folder_item.setIcon(QIcon(os.path.join("assets", "uisvg", "folder.svg")))
            folder_item.setData(f"VIRTUAL_GROUP_{folder_name}", Qt.ItemDataRole.UserRole)
            folder_item.setData(True, Qt.ItemDataRole.UserRole + 2) 
            folder_item.setData(True, Qt.ItemDataRole.UserRole + 4) 
            
            for f_path, f_name, media_type in files:
                is_vid = media_type == "video" or (media_type == "image" and any(f_name.lower().endswith(e) for e in self.clean_vid_exts))
                file_item = self.create_file_item(f_name, f_path, is_vid)
                folder_item.appendRow(file_item)
                
            self.search_render_root.appendRow(folder_item)
            rendered += len(files) 

        # 3. Dispatch thumbnails to the background worker for this batch
        if files_for_img_thumbs: self.thumb_worker.add_to_queue(files_for_img_thumbs)
        if files_for_vid_thumbs: self.vid_thumb_worker.add_to_queue(files_for_vid_thumbs)

        # 4. Check if we are done or need another loop
        if self.search_render_results or self.search_render_folders:
            # Update the loading text to show progress
            left = len(self.search_render_results)
            self.ui.lbl_placeholder.setText(f"⏳ Rendering... {left} remaining")
            
            # Run this function again in 5 milliseconds
            QTimer.singleShot(5, self.render_search_batch)
        else:
            # Finished! Hide the placeholder and expand the tree
            self.ui.lbl_placeholder.hide()
            proxy_index = self.proxy_model.mapFromSource(self.search_render_root.index())
            self.ui.tree_view.expand(proxy_index)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and os.path.isdir(url.toLocalFile()):
                    event.acceptProposedAction()
                    return
        event.ignore()


    def dragMoveEvent(self, event):
        event.acceptProposedAction()


    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if os.path.isdir(path):
                    self.load_root_folder(path)
                    break

        event.acceptProposedAction()            

    def flash_button_icon(self, button, icon_name, duration=150):
        # 🔹 Change "Svg2" to "svg2" and "Svg" to "svg" if your real folders are lowercase!
        active_icon = QIcon(os.path.join(self.asset_dir, "svg2", f"{icon_name}.svg"))
        default_icon = QIcon(os.path.join(self.asset_dir, "svg", f"{icon_name}.svg"))

        button.setIcon(active_icon)
        QTimer.singleShot(duration, lambda: button.setIcon(default_icon))  


    # ==========================================
    # DATABASE LOGIC
    # ==========================================
    def auto_load_database(self):
        from PyQt6.QtCore import QSettings
        from PyQt6.QtWidgets import QDialog, QMessageBox
        from Src.Dialogs.setup_dialog import FirstTimeSetupDialog
        
        settings = QSettings("MediaNest", "AppConfig")
        db_folder = settings.value("db_folder_path", "", type=str)
        
        # 1. If they haven't set up the workspace, show the Setup Popup!
        if not db_folder or not os.path.exists(db_folder):
            setup_window = FirstTimeSetupDialog(self)
            
            if setup_window.exec() == QDialog.DialogCode.Accepted:
                # User successfully finished setup. Grab the new path!
                db_folder = settings.value("db_folder_path", "", type=str)
            else:
                # User clicked 'Cancel' or 'X', just abort silently
                return

        # 2. Path exists (or was just created), load the database!
        db_path = os.path.join(db_folder, "library.db")
        if os.path.exists(db_path):
            self.connect_to_database(db_path)
        else:
            QMessageBox.critical(self, "Error", f"Could not find library.db in:\n{db_folder}")

    def connect_to_database(self, db_path):
        """Establishes the SQLite connection and updates the UI."""
        try:
            self.current_db_path = db_path
            self.db_connection = sqlite3.connect(db_path, check_same_thread=False)
            
            # ==========================================
            # LOAD TAGS AND SETUP AUTOCOMPLETE
            # ==========================================
            cursor = self.db_connection.cursor()
            cursor.execute("SELECT tag_name FROM Tags")
            # Fetch all unique tags
            all_tags = set([row[0] for row in cursor.fetchall()])
            
            # 🔹 Also fetch artists from MangaGalleries so they act as tags!
            try:
                cursor.execute("SELECT DISTINCT artist FROM MangaGalleries WHERE artist IS NOT NULL AND artist != ''")
                artists = [row[0] for row in cursor.fetchall()]
                all_tags.update(artists)
            except sqlite3.OperationalError:
                pass # In case MangaGalleries table doesn't exist yet
                
            all_tags = sorted(list(all_tags))
            
            self.tag_completer = MultiTagCompleter(all_tags, self)
            
            # ==========================================
            # SCALE-AWARE DROPDOWN STYLING
            # ==========================================
            # Check the current scale so we can prevent dotted/blurry text!
            try:
                current_scale = float(os.environ.get("QT_SCALE_FACTOR", "1.0"))
                if current_scale < 1.0:
                    # If scaled down, make the font bolder and slightly larger to survive the shrink
                    font_style = "font-size: 14px; font-weight: bold;"
                else:
                    font_style = "font-size: 13px; font-weight: normal;"
            except Exception:
                font_style = "font-size: 13px; font-weight: normal;"

            # Style the dropdown menu (using an f-string to inject our dynamic font)
            self.tag_completer.popup().setStyleSheet(f"""
                QListView {{
                    background-color: #252526;
                    color: white;
                    border: 1px solid #3e3e42;
                    {font_style}
                    padding: 5px;
                }}
                QListView::item {{
                    padding: 6px;
                    border-radius: 4px;
                }}
                QListView::item:hover, QListView::item:selected {{
                    background-color: #007acc;
                }}
            """)
            # ==========================================
            
            # Attach it to the search bar
            self.ui.search_bar.setCompleter(self.tag_completer)

            # Change the button to show it was successful!
            self.ui.btn_load_db.setText(" DB ACTIVE")
            self.ui.btn_load_db.setStyleSheet("""
                QPushButton {
                    background-color: #8957e5;
                    color: white;
                    border-radius: 10px; 
                    font-weight: bold;
                    font-size: 14px;  
                    padding: 0px 20px;  
                }
            """)
            print(f"Successfully connected to database at: {db_path}")
            print(f"Loaded {len(all_tags)} unique tags into the autocomplete engine.")
            
        except Exception as e:
            print(f"Failed to load database: {e}")
            self.db_connection = None