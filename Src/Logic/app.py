import sys
import os

if sys.platform == "win32":
    # Force the Windows Media Foundation backend for hardware-accelerated 4K playback on low-end CPUs
    os.environ["QT_MEDIA_BACKEND"] = "windows"

import io
import time
import json
import sqlite3
import hashlib
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
from PyQt6.QtWidgets import (QMainWindow, QFileDialog, QApplication, QMenu, 
                             QStyledItemDelegate, QStyle, QListWidgetItem,
                             QCompleter, QMessageBox, QVBoxLayout, QWidget, QListWidget,
                             QLineEdit, QDialog)
from PyQt6.QtGui import (QPixmap, QIcon, QAction, QStandardItemModel, 
                         QStandardItem, QColor, QPainter, QImageReader, QImage, QMovie,
                         QKeySequence, QShortcut, QIcon)
from PyQt6.QtCore import ( QStringListModel,
QDir, QUrl, Qt, QRect, QEvent, pyqtSignal, QTimer, 
                          QThread, QObject, QSize, QSortFilterProxyModel, QBuffer, QByteArray,
                          QSettings, QPoint)

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink
from collections import defaultdict

from Src.Ui.interface import MainWindowUI
from Src.Ui.theme import VSCODE_DARK_THEME
from Src.Logic.file_ops import FileContextMenu
from Src.Logic.paths import resource_path
from Src.Dialogs.settings_dialog import SettingsDialog
from Src.Ui.theme import VSCODE_DARK_THEME
from Src.Dialogs.setup_dialog import FirstTimeSetupDialog
from Src.Dialogs.support_dialog import SupportDialog

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
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        
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
            
        appdata_path = os.environ.get('APPDATA')
        if not appdata_path:
            appdata_path = os.path.expanduser('~')
        cache_dir = os.path.join(appdata_path, 'MediaNest', 'ThumbCache')
        os.makedirs(cache_dir, exist_ok=True)
        
        path_hash = hashlib.md5(self.current_path.encode('utf-8')).hexdigest()
        cache_file_path = os.path.join(cache_dir, f"{path_hash}.jpg")

        if os.path.exists(cache_file_path):
            cached_image = QImage(cache_file_path)
            if not cached_image.isNull():
                self.thumbnail_ready.emit(self.current_path, cached_image)
                self.current_path = None
                self.is_processing = False
                QTimer.singleShot(10, self.process_next)
                return
        
        self.player.setSource(QUrl.fromLocalFile(self.current_path))
        self.timeout_timer.start(3000)
        self.timeout_timer.start(3000)

    def pause(self):
        self.is_paused = True
        if self.is_processing:
            self.player.stop()
            self.timeout_timer.stop()
            self.is_processing = False
            if getattr(self, 'current_path', None):
                self.queue.insert(0, self.current_path)
                self.current_path = None

    def resume(self):
        self.is_paused = False
        if not self.is_processing and self.queue:
            self.process_next()

    def on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            if not self.is_processing or not self.current_path:
                return
            duration = self.player.duration()
            if duration > 0:
                seek_pos = min(15000, int(duration * 0.15))
                self.player.setPosition(seek_pos)
            self.player.play()

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
                
        appdata_path = os.environ.get('APPDATA')
        if not appdata_path:
            appdata_path = os.path.expanduser('~')
        cache_dir = os.path.join(appdata_path, 'MediaNest', 'ThumbCache')
        os.makedirs(cache_dir, exist_ok=True)
        
        path_hash = hashlib.md5(path_to_emit.encode('utf-8')).hexdigest()
        cache_file_path = os.path.join(cache_dir, f"{path_hash}.jpg")
        final_image.save(cache_file_path, "JPG", 85)
        
        self.thumbnail_ready.emit(path_to_emit, final_image)
        QTimer.singleShot(10, self.process_next)

    def on_timeout(self):
        self.player.stop()
        self.player.setSource(QUrl())
        self.current_path = None
        self.process_next()

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
            
            if path.startswith("custom_manga:"):
                parts = path.split("|")
                if len(parts) >= 2:
                    target_path = parts[1]
                    is_gallery = True
            
            if is_gallery:
                try:
                    for entry in os.scandir(path):
                        if entry.is_file() and entry.name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                            target_path = entry.path
                            break
                except OSError:
                    pass

            path_hash = hashlib.md5(path.encode('utf-8')).hexdigest()
            cache_file_path = os.path.join(self.cache_dir, f"{path_hash}.jpg")

            if os.path.exists(cache_file_path):
                cached_image = QImage(cache_file_path)
                if not cached_image.isNull():
                    self.thumbnail_ready.emit(path, cached_image)
                    time.sleep(0.005)
                    continue

            try:
                
                
                loaded_image = QImage()
                with Image.open(target_path) as pil_img:
                    pil_img.thumbnail((TARGET_SIZE, TARGET_SIZE))
                    
                    if pil_img.mode in ("RGBA", "P"):
                        pil_img = pil_img.convert("RGB")
                    
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG", quality=85)
                    buf.seek(0)
                    loaded_image.loadFromData(buf.read(), "JPG")
                
                if not loaded_image.isNull():
                    final_image = QImage(TARGET_SIZE, TARGET_SIZE, QImage.Format.Format_ARGB32)
                    final_image.fill(Qt.GlobalColor.transparent)

                    painter = QPainter(final_image)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    
                    if is_gallery:
                        w = loaded_image.width()
                        h = loaded_image.height()
                        
                        painter.save()
                        painter.translate(TARGET_SIZE//2 - 6, TARGET_SIZE//2 + 8)
                        painter.rotate(-12)
                        painter.fillRect(QRect(-w//2, -h//2, w, h), Qt.GlobalColor.white)
                        painter.setPen(QColor(0, 0, 0, 70))
                        painter.drawRect(QRect(-w//2, -h//2, w, h))
                        painter.restore()
                        
                        painter.save()
                        painter.translate(TARGET_SIZE//2 + 8, TARGET_SIZE//2 - 4)
                        painter.rotate(9)
                        painter.fillRect(QRect(-w//2, -h//2, w, h), Qt.GlobalColor.white)
                        painter.setPen(QColor(0, 0, 0, 70))
                        painter.drawRect(QRect(-w//2, -h//2, w, h))
                        painter.restore()

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
            except Exception as e:
                print(f"[ThumbThread] Error generating thumbnail for {path}: {e}")

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
        
        if perf_mode == "high":
            self.thread_count = 8
        elif perf_mode == "low":
            self.thread_count = 1
        else:
            self.thread_count = 4
            
        self.threads = []
        self.current_idx = 0

        for _ in range(self.thread_count):
            t = SingleThumbnailThread(perf_mode)
            t.thumbnail_ready.connect(self.thumbnail_ready.emit)
            self.threads.append(t)

    def start(self):
        for t in self.threads:
            t.start()

    def setPriority(self, priority):
        for t in self.threads:
            t.setPriority(priority)

    def add_to_queue(self, path_list):
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

    @property
    def queue(self):
        return [p for t in self.threads for p in t.queue]
        
    @queue.setter
    def queue(self, new_queue):
        self.clear_queue()
        self.add_to_queue(new_queue)


class FileSizeBackfillWorker(QThread):
    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path

    def run(self):
        try:
            import os
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()

            # Process Images table
            cursor.execute("SELECT hash, file_path FROM Images WHERE file_size IS NULL")
            rows = cursor.fetchall()
            updates = []
            for h, p in rows:
                if os.path.exists(p):
                    updates.append((os.path.getsize(p), h))
            
            if updates:
                cursor.executemany("UPDATE Images SET file_size = ? WHERE hash = ?", updates)
                conn.commit()

            # Process tagless table
            cursor.execute("SELECT hash, file_path FROM tagless WHERE file_size IS NULL")
            rows = cursor.fetchall()
            updates = []
            for h, p in rows:
                if os.path.exists(p):
                    updates.append((os.path.getsize(p), h))

            if updates:
                cursor.executemany("UPDATE tagless SET file_size = ? WHERE hash = ?", updates)
                conn.commit()

            conn.close()
        except Exception as e:
            print(f"File size backfill failed: {e}")


class FileSizeBackfillWorker(QThread):
    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path

    def run(self):
        try:
            import os
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()

            # Process Images table
            cursor.execute("SELECT hash, file_path FROM Images WHERE file_size IS NULL")
            rows = cursor.fetchall()
            updates = []
            for h, p in rows:
                if os.path.exists(p):
                    updates.append((os.path.getsize(p), h))
            
            if updates:
                cursor.executemany("UPDATE Images SET file_size = ? WHERE hash = ?", updates)
                conn.commit()

            # Process tagless table
            cursor.execute("SELECT hash, file_path FROM tagless WHERE file_size IS NULL")
            rows = cursor.fetchall()
            updates = []
            for h, p in rows:
                if os.path.exists(p):
                    updates.append((os.path.getsize(p), h))

            if updates:
                cursor.executemany("UPDATE tagless SET file_size = ? WHERE hash = ?", updates)
                conn.commit()

            conn.close()
        except Exception as e:
            print(f"File size backfill failed: {e}")

class DatabaseSearchWorker(QThread):
    search_finished = pyqtSignal(list, dict, str, bool, int) 
    error_occurred = pyqtSignal(str)

    def __init__(self, db_path, search_text, limit, offset, search_id, filter_type="All"):
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
            import re
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()

            raw_tags = [t.strip() for t in self.search_text.split(',') if t.strip()]
            req_tags, opt_tags = [], []
            sys_filters = []

            for t in raw_tags:
                is_or = t.startswith('~')
                clean_tag = t[1:].strip() if is_or else t
                
                if clean_tag.lower().startswith("system:size"):
                    match = re.search(r'([><=]+)\s*(.*)', clean_tag.split(':', 1)[1])
                    if match:
                        op = match.group(1)
                        if op == '==': op = '='
                        if op in ('>', '<', '=', '>=', '<=', '!=', '<>'):
                            size_str = match.group(2).lower().strip()
                            smatch = re.match(r'([\d.]+)\s*([a-z]*)', size_str)
                            if smatch:
                                val = float(smatch.group(1))
                                unit = smatch.group(2)
                                multiplier = 1
                                if unit in ('kb', 'k'): multiplier = 1024
                                elif unit in ('mb', 'm'): multiplier = 1024**2
                                elif unit in ('gb', 'g'): multiplier = 1024**3
                                sys_filters.append(f"Images.file_size {op} {int(val * multiplier)}")
                    continue
                
                if ":" in clean_tag:
                    clean_tag = clean_tag.split(":", 1)[1].strip()
                    
                clean_tag = clean_tag.replace(' ', '_')
                if clean_tag:
                    if is_or: opt_tags.append(clean_tag)
                    else: req_tags.append(clean_tag)

            all_tags = req_tags + opt_tags

            if not all_tags and not sys_filters:
                self.search_finished.emit([], {}, self.search_text, False, self.search_id)
                return

            file_filter_sql = ""
            if self.filter_type == "Images":
                file_filter_sql = " AND (Images.file_name LIKE '%.jpg' OR Images.file_name LIKE '%.jpeg' OR Images.file_name LIKE '%.png' OR Images.file_name LIKE '%.gif' OR Images.file_name LIKE '%.bmp' OR Images.file_name LIKE '%.webp')"
            elif self.filter_type == "Videos":
                file_filter_sql = " AND (Images.file_name LIKE '%.mp4' OR Images.file_name LIKE '%.mkv' OR Images.file_name LIKE '%.avi' OR Images.file_name LIKE '%.mov' OR Images.file_name LIKE '%.webm')"
            
            sys_filter_sql = ""
            if sys_filters:
                sys_filter_sql = " AND " + " AND ".join(sys_filters)

            if not all_tags:
                query = f"""
                    SELECT Images.file_path, Images.file_name 
                    FROM Images
                    WHERE 1=1 {file_filter_sql} {sys_filter_sql}
                    ORDER BY Images.phash
                    LIMIT ? OFFSET ?
                """
                params = [self.limit, self.offset]
            else:
                placeholders = ', '.join(['?'] * len(all_tags))
                query = f"""
                    SELECT Images.file_path, Images.file_name 
                    FROM Images
                    JOIN ImageTags ON Images.hash = ImageTags.hash
                    JOIN Tags ON ImageTags.tag_id = Tags.tag_id
                    WHERE Tags.tag_name IN ({placeholders}){file_filter_sql} {sys_filter_sql}
                    GROUP BY Images.hash
                    HAVING 1=1
                """
                params = all_tags.copy()

            if all_tags:
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

            folders_map = defaultdict(list)
            valid_results = []

            for file_path, file_name in results:
                if not self.is_running: return
                if os.path.exists(file_path):
                    folder_name = os.path.basename(os.path.dirname(file_path))
                    folders_map[folder_name].append((file_path, file_name, "image"))
                    valid_results.append((file_path, file_name, "image"))

            if self.filter_type in ["All", "Images"]:
                if all_tags:
                    manga_query = f"""
                        WITH GalleryAllTags AS (
                            SELECT MangaTags.gallery_id, LOWER(REPLACE(Tags.tag_name, ' ', '_')) as tag
                            FROM MangaTags
                            JOIN Tags ON MangaTags.tag_id = Tags.tag_id
                            UNION
                            SELECT gallery_id, LOWER(REPLACE(artist, ' ', '_')) as tag
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
                                valid_results.append((folder_path, title, "gallery"))
                    except sqlite3.OperationalError:
                        pass

            if self.filter_type in ["All", "Images"]:
                if all_tags:
                    custom_query = f"""
                        WITH CustomAllTags AS (
                            SELECT manga_id, LOWER(REPLACE(tag_name, ' ', '_')) as tag
                            FROM CustomMangaTags
                            UNION
                            SELECT manga_id, LOWER(REPLACE(title, ' ', '_')) as tag
                            FROM CustomMangas
                        )
                        SELECT CustomMangas.manga_id, CustomMangas.title, CustomMangas.cover_image
                        FROM CustomMangas
                        JOIN CustomAllTags ON CustomMangas.manga_id = CustomAllTags.manga_id
                        WHERE CustomAllTags.tag IN ({placeholders})
                        GROUP BY CustomMangas.manga_id
                        HAVING 1=1
                    """
                    custom_params = all_tags.copy()
                    if req_tags:
                        custom_query += f" AND SUM(CASE WHEN CustomAllTags.tag IN ({req_placeholders}) THEN 1 ELSE 0 END) = ?"
                        custom_params.extend(req_tags)
                        custom_params.append(len(req_tags))
                    if opt_tags:
                        custom_query += f" AND SUM(CASE WHEN CustomAllTags.tag IN ({opt_placeholders}) THEN 1 ELSE 0 END) > 0"
                        custom_params.extend(opt_tags)
                    custom_query += " LIMIT ? OFFSET ?"
                    custom_params.extend([self.limit, self.offset])

                    try:
                        cursor.execute(custom_query, custom_params)
                        custom_results = cursor.fetchall()
                        for manga_id, title, cover_image in custom_results:
                            if not self.is_running: return
                            
                            cursor2 = conn.cursor()
                            cursor2.execute("SELECT image_path FROM CustomMangaPages WHERE manga_id = ? AND image_path != ? ORDER BY page_number ASC LIMIT 3", (manga_id, cover_image))
                            extra_pages = [r[0] for r in cursor2.fetchall()]
                            
                            custom_path = f"custom_manga:{manga_id}|{cover_image}"
                            for ex in extra_pages:
                                custom_path += f"|{ex}"
                                
                            if os.path.exists(cover_image):
                                valid_results.append((custom_path, title, "gallery"))
                    except sqlite3.OperationalError:
                        pass

            is_appending = self.offset > 0
            self.search_finished.emit(valid_results, dict(folders_map), self.search_text, is_appending, self.search_id)
            conn.close()

        except Exception as e:
            self.error_occurred.emit(str(e))

    def stop(self):
        self.is_running = False

class TagFetchWorker(QThread):
    tags_fetched = pyqtSignal(list)
    
    def __init__(self, db_path, file_path):
        super().__init__()
        self.db_path = db_path
        self.file_path = file_path
        self.is_running = True

    def run(self):
        try:
            
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()
            
            tags = []
            
            if not self.file_path.startswith("custom_manga:"):
                query = """
                    SELECT Tags.tag_name 
                    FROM Tags
                    JOIN ImageTags ON Tags.tag_id = ImageTags.tag_id
                    JOIN Images ON ImageTags.hash = Images.hash
                    WHERE Images.file_path = ?
                """
                cursor.execute(query, (self.file_path,))
                tags = [r[0] for r in cursor.fetchall()]
                
                if not tags and os.path.isdir(self.file_path):
                    manga_query = """
                        SELECT Tags.tag_name
                        FROM Tags
                        JOIN MangaTags ON Tags.tag_id = MangaTags.tag_id
                        JOIN MangaGalleries ON MangaGalleries.gallery_id = MangaTags.gallery_id
                        WHERE MangaGalleries.folder_path = ?
                    """
                    cursor.execute(manga_query, (self.file_path,))
                    tags = [r[0] for r in cursor.fetchall()]
            
            if self.is_running:
                self.tags_fetched.emit(tags)
                
            conn.close()
        except Exception:
            if self.is_running:
                self.tags_fetched.emit([])

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

class NsTabExpander(QObject):
    """
    Shows inline ghost text for namespace aliases directly in the input field.
    """
    FULL_NS = ['character:', 'series:', 'artist:', 'metadata:', 'general:', 'system:size ']
    
    NS_MIN_LEN = {
        'character:': 4,
        'series:':    3,
        'artist:':    3,
        'metadata:':  4,
        'general:':   3,
        'system:size ': 4,
    }

    def __init__(self, widget, parent=None):
        super().__init__(parent)
        self.widget = widget
        widget.textEdited.connect(self._on_text_edited)

    def _get_last_term_info(self, full_text, cursor_pos):
        text_before = full_text[:cursor_pos]
        if ',' in text_before:
            comma_pos = text_before.rfind(',')
            prefix = full_text[:comma_pos + 1] + ' '
            last_term = text_before[comma_pos + 1:].lstrip()
        else:
            prefix = ''
            last_term = text_before.lstrip()
        return prefix, last_term

    def _find_ns_completion(self, term):
        if not term or ':' in term:
            return None
        term_lower = term.lower()
        matches = [ns for ns in self.FULL_NS if ns.startswith(term_lower) and ns != term_lower]
        if len(matches) == 1:
            ns = matches[0]
            if len(term_lower) >= self.NS_MIN_LEN.get(ns, 3):
                return ns
        return None

    def _on_text_edited(self, text):
        cursor_pos = self.widget.cursorPosition()
        prefix, last_term = self._get_last_term_info(text, cursor_pos)

        match = self._find_ns_completion(last_term)
        if match:
            new_text = prefix + match
            typed_end = len(prefix) + len(last_term)
            self.widget.blockSignals(True)
            self.widget.setText(new_text)
            self.widget.setSelection(typed_end, len(new_text) - typed_end)
            self.widget.blockSignals(False)
            # Emit textEdited so the completer knows the text has expanded to the full namespace.
            # This makes DbLookupCompleter see "character:" instead of "char", causing its 
            # search term to be empty (""), which closes the popup and prevents it from stealing the Tab key.
            self.widget.textEdited.emit(new_text)

    def eventFilter(self, obj, event):
        if obj is not self.widget:
            return False
            
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Backspace:
                if self.widget.hasSelectedText():
                    sel_start = self.widget.selectionStart()
                    sel_length = self.widget.selectionLength()
                    text = self.widget.text()
                    if sel_start > 0 and (sel_start + sel_length == len(text)):
                        new_text = text[:sel_start - 1]
                        self.widget.setText(new_text)
                        self.widget.setCursorPosition(len(new_text))
                        return True
        return False

class NsColorModel(QStringListModel):
    def data(self, index, role):
        if role == Qt.ItemDataRole.ForegroundRole:
            text = super().data(index, Qt.ItemDataRole.DisplayRole)
            if text and ":" in text:
                ns = text.split(":", 1)[0].lower()
                colors = {
                    'character': QColor(0, 255, 0),
                    'series': QColor(255, 0, 255),
                    'artist': QColor(255, 255, 0),
                    'metadata': QColor(255, 165, 0)
                }
                return colors.get(ns, QColor(200, 200, 200))
            return QColor(200, 200, 200)
        return super().data(index, role)

class MultiTagCompleter(QCompleter):
    NS_ALIASES = {
        'char': 'character:', 'character': 'character:',
        'ser': 'series:', 'series': 'series:',
        'art': 'artist:', 'artist': 'artist:',
        'meta': 'metadata:', 'metadata': 'metadata:',
        'gen': 'general:', 'general': 'general:',
    }

    def __init__(self, tags, parent=None):
        self._all_tags = list(tags)
        super().__init__(self._all_tags, parent)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterMode(Qt.MatchFlag.MatchContains)

    def _get_last_term(self, text):
        if ',' in text:
            return text.split(',')[-1].lstrip()
        return text.lstrip()

    def _filtered_tags(self, namespace):
        prefix = f"{namespace}:"
        return [t[len(prefix):] for t in self._all_tags if t.startswith(prefix)]

    def showPopup(self):
        super().showPopup()
        popup = self.popup()
        search_bar = self.widget()
        if popup and search_bar:
            global_pos = search_bar.mapToGlobal(QPoint(0, search_bar.height()))
            popup.move(global_pos)
            popup.setFixedWidth(search_bar.width())

    def pathFromIndex(self, index):
        suggestion = super().pathFromIndex(index)
        current_text = self.widget().text()
        last_term = self._get_last_term(current_text)

        if suggestion in self.NS_ALIASES:
            expanded = self.NS_ALIASES[suggestion]
            if ',' in current_text:
                prefix = current_text[:current_text.rfind(',')]
                return f"{prefix}, {expanded}"
            return expanded

        _KNOWN_NS = ('character:', 'series:', 'artist:', 'metadata:', 'general:')

        if ':' in last_term:
            ns_part, _ = last_term.split(':', 1)
            if any(suggestion.startswith(ns) for ns in _KNOWN_NS):
                full_suggestion = suggestion
            else:
                full_suggestion = f"{ns_part}:{suggestion}"
        else:
            full_suggestion = suggestion

        if ',' in current_text:
            prefix = current_text[:current_text.rfind(',')]
            if last_term.startswith('~'):
                return f"{prefix}, ~{full_suggestion}"
            return f"{prefix}, {full_suggestion}"

        if current_text.strip().startswith('~'):
            return f"~{full_suggestion}"

        return full_suggestion

    def splitPath(self, path):
        last_term = self._get_last_term(path)

        if last_term.startswith('~'):
            last_term = last_term[1:]

        if ':' in last_term:
            ns_part, tag_part = last_term.split(':', 1)
            ns_part = ns_part.strip().lower()
            filtered = self._filtered_tags(ns_part)
            self.model().setStringList(filtered)
            return [tag_part]

        self.model().setStringList(self._all_tags)
        return [last_term]

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

class FolderButtonDelegate(QStyledItemDelegate):
    button_clicked = pyqtSignal(object)
   
    def paint(self, painter, option, index):
        super().paint(painter, option, index)

        is_folder = index.data(Qt.ItemDataRole.UserRole + 2)
        has_subfolders = index.data(Qt.ItemDataRole.UserRole + 6)
        is_flat_root = index.data(Qt.ItemDataRole.UserRole + 4)

        if not ((is_folder and has_subfolders) or is_flat_root):
            return

        main_window = self.parent().window()

        if not hasattr(main_window, "icon_folder_closed"):
            return

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

        ICON_SIZE = 20
        BUTTON_W  = 30

        button_rect = QRect(
            option.rect.right() - BUTTON_W,
            option.rect.top(),
            BUTTON_W,
            option.rect.height()
        )

        painter.save()

        x = button_rect.center().x() - ICON_SIZE // 2
        y = option.rect.center().y() - ICON_SIZE // 2

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
        
        self.setStyleSheet(VSCODE_DARK_THEME)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

    def closeEvent(self, event):
        self.main_app.reattach_viewer()
        event.accept()

class MediaExplorerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self._is_toggling_fullscreen = False
        self.ui = MainWindowUI()
        self.image_cache = {}
        self.ui.setup_ui(self)
        self.setWindowTitle("Media Nest V3.0.0")
        theme = VSCODE_DARK_THEME

        try:
            current_scale = float(os.environ.get("QT_SCALE_FACTOR", "1.0"))

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
            pass

        # Patch theme font-size from saved config at startup
        try:
            import re as _re
            if getattr(sys, 'frozen', False):
                _base = os.path.dirname(sys.executable)
            else:
                _base = os.path.abspath(".")
            _cfg_path = os.path.join(_base, "config.json")
            if os.path.exists(_cfg_path):
                with open(_cfg_path, "r") as _f:
                    _cfg = json.load(_f)
                    _fs = _cfg.get("font_size", None)
                    if _fs:
                        theme = _re.sub(
                            r'(QWidget\s*\{[^}]*?font-size\s*:\s*)\d+px',
                            lambda m: m.group(1) + f"{int(_fs)}px",
                            theme,
                            flags=_re.DOTALL
                        )
        except Exception:
            pass

        self.setStyleSheet(theme)

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
        
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300)
        self.search_timer.timeout.connect(self.process_search)
        self.clear_player_timer = QTimer(self)
        self.clear_player_timer.setSingleShot(True) 
        self.clear_player_timer.timeout.connect(self.clear_media_viewer)

        self.ui.search_bar.textEdited.connect(self.on_search_bar_typed)
        self.ui.search_bar.returnPressed.connect(self.force_instant_search)

        self.delegate = FolderButtonDelegate(self.ui.tree_view)
        self.delegate.button_clicked.connect(self.on_folder_toggle)
        self.ui.tree_view.setItemDelegate(self.delegate)

        self.ui.btn_open.clicked.connect(self.open_folder_dialog)
        self.db_connection = None 
        self.ui.btn_load_db.clicked.connect(self.auto_load_database)
        self.ui.btn_change_db.clicked.connect(self.open_settings_dialog)        
        self.ui.btn_detach.clicked.connect(self.toggle_detached_viewer)
        self.ui.btn_support.clicked.connect(self.open_support_dialog)
        self.floating_viewer = None
        self.ui.tree_view.expanded.connect(self.on_item_expanded)
        self.ui.tree_view.clicked.connect(self.on_tree_item_clicked)

        # Wire the File Info panel close button to return to the Tags view
        self.ui.file_info_panel.btn_close.clicked.connect(self._on_file_info_closed)
        
        self.ui.gallery_section.list_widget.currentItemChanged.connect(self.on_gallery_item_changed)
        self.ui.btn_add_tag_main.clicked.connect(self.add_main_tag)
        self.ui.input_new_tag.returnPressed.connect(self.add_main_tag)
        self.ui.btn_delete_tag_main.clicked.connect(self.delete_main_tag)
        self.ui.tag_list_widget.customContextMenuRequested.connect(self.show_tag_context_menu)
        if hasattr(self.ui.gallery_section, 'filter_combo'):
            self.ui.gallery_section.filter_combo.currentTextChanged.connect(self.on_filter_changed)
        if hasattr(self.ui.gallery_section, 'name_filter_input'):
            self.ui.gallery_section.name_filter_input.textChanged.connect(self.apply_gallery_filter)
        self.current_image_path = None
        
        self.ui.gallery_section.list_widget.setUniformItemSizes(True)
        self.ui.gallery_section.list_widget.setGridSize(QSize(250, 270))
        self.ui.gallery_section.list_widget.setLayoutMode(QListWidget.LayoutMode.Batched)
        self.ui.gallery_section.list_widget.setBatchSize(50)
        
        self.ui.gallery_section.list_widget.verticalScrollBar().valueChanged.connect(self.on_gallery_scroll)
        self.is_fetching_data = False 
        
        self.current_gallery_folder = None 
        self.scanner_thread = None
        self.loading_item_ref = None 
        
        self.current_search_offset = 0
        self.current_search_id = 0

        perf_mode = "balanced"
        
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

                    # Apply saved font size immediately at startup
                    saved_font_size = config.get("font_size", None)
                    if saved_font_size:
                        app_instance = QApplication.instance()
                        if app_instance:
                            from PyQt6.QtGui import QFont
                            _px = int(saved_font_size)
                            _pt = max(1, round(_px * 72 / 96))
                            app_instance.setFont(QFont("Segoe UI", _pt))
            except Exception:
                pass
        self.current_perf_mode = perf_mode
        self.last_mouse_button = Qt.MouseButton.LeftButton

        self.thumbnail_map = {} 
        self.thumb_worker = ThumbnailWorker(perf_mode=perf_mode)
        self.thumb_worker.thumbnail_ready.connect(self.on_thumbnail_ready)
        self.thumb_worker.start()
        
        if perf_mode == "high":
            self.thumb_worker.setPriority(QThread.Priority.HighestPriority)
        elif perf_mode == "low":
            self.thumb_worker.setPriority(QThread.Priority.LowestPriority)
        else:
            self.thumb_worker.setPriority(QThread.Priority.LowPriority)
        
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
        if hasattr(self, 'media_player'):
            self.media_player.stop()
            
        if hasattr(self, 'settings_dialog'):
            self.settings_dialog.close()
            
        if hasattr(self, 'thumb_worker'):
            self.thumb_worker.stop()

        if hasattr(self, 'vid_thumb_worker'):
            self.vid_thumb_worker.queue.clear()
            self.vid_thumb_worker.is_processing = False
            if hasattr(self.vid_thumb_worker, 'player'):
                self.vid_thumb_worker.player.stop()
            if hasattr(self.vid_thumb_worker, 'timeout_timer'):
                self.vid_thumb_worker.timeout_timer.stop()

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

        self.ui.btn_play.clicked.connect(self.toggle_play_pause)
        self.ui.btn_skip_backward.clicked.connect(self.skip_backward)
        self.ui.btn_skip_forward.clicked.connect(self.skip_forward)
        self.ui.btn_fullscreen.clicked.connect(self.toggle_fullscreen)        
        
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
            self.ui.btn_loop.setIcon(
                QIcon(os.path.join(self.asset_dir, "Svg2", "repeat.svg"))
            )
        else:
            self.ui.btn_loop.setIcon(
                QIcon(os.path.join(self.asset_dir, "Svg", "repeat-off.svg"))
            )

    def media_status_changed(self, status):
        # Auto-play as soon as the media is actually ready (avoids 0xC00D6D60)
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            if getattr(self, '_autoplay_pending', False):
                self._autoplay_pending = False
                self.media_player.play()

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

        if not hasattr(self, 'original_sidebar_width'):
            self.original_sidebar_width = self.ui.sidebar_widget.maximumWidth()
            
        self.ui.sidebar_widget.setMaximumWidth(16777215) 
        self.ui.horizontal_splitter.setSizes([400, 800])
        
        self.previous_gallery_mode = self.ui.gallery_section.current_mode
        if hasattr(self.ui.gallery_section, 'set_size_mode'):
            self.ui.gallery_section.set_size_mode("small")

    def reattach_viewer(self):
        """Pulls the viewer back into the main app and restores the UI layout."""
        if self.floating_viewer:
            
            if hasattr(self, 'original_sidebar_width'):
                self.ui.sidebar_widget.setMaximumWidth(self.original_sidebar_width)
            
            self.ui.vertical_splitter.insertWidget(0, self.ui.viewer_widget)
            self.ui.vertical_splitter.setSizes([600, 200])
            self.ui.horizontal_splitter.setSizes([320, 880])
            
            if hasattr(self, 'previous_gallery_mode') and hasattr(self.ui.gallery_section, 'set_size_mode'):
                self.ui.gallery_section.set_size_mode(self.previous_gallery_mode)
            
            self.floating_viewer.deleteLater()
            self.floating_viewer = None
            
            self.ui.btn_detach.setText("⧉")
            self.ui.btn_detach.setToolTip("Detach Viewer (Multi-Monitor)")

    def on_filter_changed(self, text):
        """Triggers when the user changes the Dropdown."""
        self.apply_gallery_filter()
        
        if getattr(self, 'db_connection', None) and self.ui.search_bar.text().strip():
            self.process_search()

    def apply_gallery_filter(self, *args):
        """Hides or shows gallery items based on the active dropdown filter AND name search."""
        if not hasattr(self.ui.gallery_section, 'filter_combo'):
            return
            
        filter_type = self.ui.gallery_section.filter_combo.currentText()
        
        name_query = ""
        if hasattr(self.ui.gallery_section, 'name_filter_input'):
            name_query = self.ui.gallery_section.name_filter_input.text().strip().lower()
            
        list_widget = self.ui.gallery_section.list_widget
        
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if not item: continue
            
            text = item.text()
            text_lower = text.lower()
            
            matches_name = True
            if name_query:
                matches_name = name_query in text_lower
                
            matches_type = True
            if filter_type != "All":
                file_path = item.data(Qt.ItemDataRole.UserRole)
                if file_path:
                    file_path_lower = file_path.lower()
                    if filter_type == "Images":
                        matches_type = any(file_path_lower.endswith(e) for e in self.clean_img_exts)
                    elif filter_type == "Videos":
                        matches_type = any(file_path_lower.endswith(e) for e in self.clean_vid_exts)
                
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
            
            if getattr(self, "current_perf_mode", "balanced") != "high":
                if hasattr(self, "thumb_worker"):
                    self.thumb_worker.pause()
                if hasattr(self, "vid_thumb_worker") and hasattr(self.vid_thumb_worker, "pause"):
                    self.vid_thumb_worker.pause()
        else:
            self.ui.video_container.btn_play.setIcon(self.get_icon("play"))
            
            if hasattr(self, "thumb_worker"):
                self.thumb_worker.resume()
            if hasattr(self, "vid_thumb_worker") and hasattr(self.vid_thumb_worker, "resume"):
                self.vid_thumb_worker.resume()

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
        
        appdata_path = os.environ.get('APPDATA', os.path.expanduser('~'))
        config_path = os.path.join(appdata_path, 'MediaNest', 'config.json')
        
        dialog = SettingsDialog(config_path, self)
        
        if dialog.exec():
            if dialog.db_folder_changed:
                if getattr(self, 'db_connection', None):
                    try:
                        self.db_connection.close()
                    except Exception:
                        pass
                
                self.connect_to_database(dialog.new_db_path)
            
            if hasattr(dialog, 'current_perf_mode'):
                self.current_perf_mode = dialog.current_perf_mode

    def open_support_dialog(self):
        """Opens the Support & Community dialog."""
        dialog = SupportDialog(self)
        dialog.exec()


    def show_file_info_panel(self, path):
        """Populates the File Info panel and swaps it in place of the Tags section."""
        import datetime

        panel = self.ui.file_info_panel

        # Strip custom_manga: prefix if present
        display_path = path
        if display_path.startswith("custom_manga:"):
            parts = display_path.split("|")
            if len(parts) >= 2:
                display_path = parts[1]

        # Default values
        name = size_str = mod_str = resolution_str = duration_str = "—"
        ftype = "—"

        try:
            name = os.path.basename(display_path) or display_path
            ext_lower = os.path.splitext(display_path)[1].lower()

            # ── File type & size ──────────────────────────────────────────
            if os.path.isdir(display_path):
                ftype = "Folder"
                try:
                    count = sum(1 for _ in os.scandir(display_path))
                    size_str = f"{count} item(s)"
                except OSError:
                    size_str = "—"
            else:
                ext_upper = ext_lower.upper()
                ftype = f"{ext_upper.lstrip('.')} File" if ext_upper else "File"
                try:
                    sz = os.path.getsize(display_path)
                    if sz < 1024:
                        size_str = f"{sz} B"
                    elif sz < 1024 ** 2:
                        size_str = f"{sz / 1024:.1f} KB"
                    elif sz < 1024 ** 3:
                        size_str = f"{sz / 1024 ** 2:.2f} MB"
                    else:
                        size_str = f"{sz / 1024 ** 3:.2f} GB"
                except OSError:
                    size_str = "—"

            # ── Modified date ──────────────────────────────────────────────
            try:
                mtime = os.path.getmtime(display_path)
                mod_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d  %H:%M")
            except OSError:
                mod_str = "—"

            # ── Resolution & Duration ──────────────────────────────────────
            IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}
            VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v"}

            if ext_lower in IMAGE_EXTS and not os.path.isdir(display_path):
                try:
                    from PIL import Image as _PILImage
                    with _PILImage.open(display_path) as img:
                        w, h = img.size
                        resolution_str = f"{w} × {h} px"
                        # For animated GIFs show frame count too
                        if ext_lower == ".gif":
                            try:
                                frames = getattr(img, "n_frames", 1)
                                if frames > 1:
                                    duration_str = f"{frames} frames"
                            except Exception:
                                pass
                except Exception:
                    resolution_str = "—"

            elif ext_lower in VIDEO_EXTS and not os.path.isdir(display_path):
                # Try cv2 first (fast, no subprocess needed)
                try:
                    import cv2 as _cv2
                    cap = _cv2.VideoCapture(display_path)
                    if cap.isOpened():
                        w   = int(cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
                        h   = int(cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
                        fps = cap.get(_cv2.CAP_PROP_FPS)
                        fc  = cap.get(_cv2.CAP_PROP_FRAME_COUNT)
                        cap.release()
                        if w > 0 and h > 0:
                            resolution_str = f"{w} × {h} px"
                        if fps > 0 and fc > 0:
                            total_sec = int(fc / fps)
                            h_part, rem = divmod(total_sec, 3600)
                            m_part, s_part = divmod(rem, 60)
                            if h_part:
                                duration_str = f"{h_part}:{m_part:02}:{s_part:02}"
                            else:
                                duration_str = f"{m_part}:{s_part:02}"
                except ImportError:
                    # cv2 not installed — try ffprobe via subprocess
                    try:
                        import subprocess, json as _json
                        result = subprocess.run(
                            ["ffprobe", "-v", "quiet", "-print_format", "json",
                             "-show_streams", "-show_format", display_path],
                            capture_output=True, text=True, timeout=5
                        )
                        if result.returncode == 0:
                            data = _json.loads(result.stdout)
                            for stream in data.get("streams", []):
                                if stream.get("codec_type") == "video":
                                    w = stream.get("width", 0)
                                    h = stream.get("height", 0)
                                    if w and h:
                                        resolution_str = f"{w} × {h} px"
                                    break
                            dur = float(data.get("format", {}).get("duration", 0))
                            if dur > 0:
                                total_sec = int(dur)
                                h_part, rem = divmod(total_sec, 3600)
                                m_part, s_part = divmod(rem, 60)
                                if h_part:
                                    duration_str = f"{h_part}:{m_part:02}:{s_part:02}"
                                else:
                                    duration_str = f"{m_part}:{s_part:02}"
                    except Exception:
                        pass
                except Exception:
                    pass

        except Exception:
            display_path = path

        panel.lbl_info_name.setText(name)
        panel.lbl_info_type.setText(ftype)
        panel.lbl_info_size.setText(size_str)
        panel.lbl_info_resolution.setText(resolution_str)
        panel.lbl_info_duration.setText(duration_str)
        panel.lbl_info_modified.setText(mod_str)
        panel.lbl_info_path.setText(display_path)
        panel.lbl_info_path.setToolTip(display_path)

        # Switch the stacked widget to the File Info page
        self.ui.show_file_info_in_stack()


    def _on_file_info_closed(self):
        """Called when the × button on the File Info panel is clicked.
        If tags were visible, switch back to Tags; otherwise hide the stack."""
        has_tags = self.ui.tag_list_widget.count() > 0
        if has_tags:
            self.ui.show_tags_in_stack()
        else:
            self.ui.bottom_stack.hide()
            sizes = self.ui.sidebar_vertical_splitter.sizes()
            total = sum(sizes)
            self.ui.sidebar_vertical_splitter.setSizes([total, 0])

    def show_gallery_context_menu(self, position):
        list_widget = self.ui.gallery_section.list_widget
        item = list_widget.itemAt(position)
        
        if item:
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
            self.ui.tree_view.blockSignals(True)
            self.ui.tree_view.setCurrentIndex(index)
            self.ui.tree_view.blockSignals(False)
            
            item = self.get_source_item(index)
            selected_path = str(item.data(Qt.ItemDataRole.UserRole))
            is_folder = item.data(Qt.ItemDataRole.UserRole + 2)
            
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
        if getattr(self, 'db_connection', None) and self.ui.search_bar.text().strip():
            return "VIRTUAL_BLOCK"

        if self.ui.tree_view.hasFocus():
            idx = self.ui.tree_view.currentIndex()
            if idx.isValid():
                item = self.get_source_item(idx)
                if item:
                    path = str(item.data(Qt.ItemDataRole.UserRole))
                    
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
        self.ui.btn_fullscreen.blockSignals(True)

        if getattr(self, 'is_video_maximized', False):
            self.is_video_maximized = False
            self.ui.btn_fullscreen.setIcon(self.get_icon("fullscreen"))
            
            self.ui.video_container.showNormal()
            self.ui.viewer_layout.addWidget(self.ui.video_container)
            
            self.autohide_timer.stop()
            self.ui.video_controls.show()
            self.ui.video_container.unsetCursor()
        else:
            self.is_video_maximized = True
            self.ui.btn_fullscreen.setIcon(self.get_icon("minimize"))
            
            self.ui.video_container.setParent(None)
            
            self.ui.video_container.showFullScreen()
            self.media_player.setPlaybackRate(1.0)
            
            self.autohide_timer.start()

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

        if getattr(self, "current_image_path", None):

            current_img = os.path.normcase(
                os.path.abspath(self.current_image_path)
            )

            if current_img == target:

                movie = self.ui.lbl_image.movie()
                if movie:
                    movie.stop()
                    self.ui.lbl_image.setMovie(None)
                    movie.deleteLater()

                self.ui.lbl_image.clear()
                self.ui.lbl_image.setPixmap(QPixmap())

                self.current_image_path = None
                self.ui.image_view_container.hide()
                self.ui.lbl_placeholder.show()

                QApplication.processEvents()
                time.sleep(0.05)

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
        if hasattr(self, 'media_player'):
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            self.ui.video_container.hide()
            
            if hasattr(self, "thumb_worker"):
                self.thumb_worker.resume()
            if hasattr(self, "vid_thumb_worker") and hasattr(self.vid_thumb_worker, "resume"):
                self.vid_thumb_worker.resume()
            
        self.current_image_path = None
        movie = self.ui.lbl_image.movie()
        if movie:
            movie.stop()
            self.ui.lbl_image.setMovie(None)
        self.ui.image_view_container.hide()
        self.ui.manhwa_reader.hide()
        if hasattr(self.ui, 'manga_reader'):
            self.ui.manga_reader.hide()
            
        if hasattr(self.ui, 'bottom_stack'):
            self.ui.bottom_stack.hide()
            sizes = self.ui.sidebar_vertical_splitter.sizes()
            total = sum(sizes)
            self.ui.sidebar_vertical_splitter.setSizes([total, 0])
            
        self.ui.lbl_placeholder.setText("Select a file to view")
        self.ui.lbl_placeholder.show()

    def format_time(self, ms):
        s = round(ms / 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02}:{m:02}:{s:02}"
        return f"{m:02}:{s:02}"

    def open_folder_dialog(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder_path:
            self.load_root_folder(folder_path)

    def load_root_folder(self, path):
        if not path:
            return

        if self.model.rowCount() == 0:
            self.model.setHorizontalHeaderLabels(["Name"])

        root_name = os.path.basename(path)

        for row in range(self.model.rowCount()):
            existing_item = self.model.item(row)
            if existing_item.data(Qt.ItemDataRole.UserRole) == path:
                return

        root_item = self.create_folder_item(root_name, path)
        self.model.appendRow(root_item)

        self.populate_normal(root_item, path)

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
        item.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "folder.svg"))))
        if has_any: item.appendRow(QStandardItem("Loading..."))
        return item

    def create_file_item(self, name, path, is_video):
        item = QStandardItem(name)
        item.setData(path, Qt.ItemDataRole.UserRole)
        item.setData(False, Qt.ItemDataRole.UserRole + 2)
        svg_name = "video.svg" if is_video else "image.svg"
        item.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", svg_name))))
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
        
        if path.startswith("VIRTUAL_"):
            return
            
        if os.path.isdir(path):
            self.populate_normal(item, path)
        else:
            item.setData(True, Qt.ItemDataRole.UserRole + 5)

    def eventFilter(self, obj, event):
        try:
            if event.type() == QEvent.Type.MouseButtonPress:
                self.last_mouse_button = event.button()

            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                if getattr(self, 'is_video_maximized', False):
                    self.toggle_fullscreen()
                    return True

            if event.type() == QEvent.Type.KeyPress:
                self.last_mouse_button = Qt.MouseButton.NoButton
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

            if event.type() == QEvent.Type.MouseButtonDblClick:
                if obj == self.ui.video_widget:
                    self.toggle_fullscreen()
                    return True

            if event.type() in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress):
                if getattr(self, 'is_video_maximized', False):
                    self.show_fullscreen_controls()
                    
            return super().eventFilter(obj, event)
            
        except RuntimeError:
            return False

    def hide_fullscreen_controls(self):
        if getattr(self, 'is_video_maximized', False):
            self.ui.video_controls.hide()
            self.ui.video_container.setCursor(Qt.CursorShape.BlankCursor) 

    def show_fullscreen_controls(self):
        if getattr(self, 'is_video_maximized', False):
            if self.ui.video_controls.isHidden():
                self.ui.video_controls.show()
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

        if not parent_item:
            return

        if parent_item.data(Qt.ItemDataRole.UserRole) != folder_path:
            return

        if parent_item.rowCount() == 1 and parent_item.child(0).text() == "⏳ Scanning...":
            parent_item.removeRow(0)

        for display_name, full_path, is_vid in batch:
            parent_item.appendRow(self.create_file_item(display_name, full_path, is_vid))

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
        self.pending_thumbnails[path] = qimage

    def apply_pending_thumbnails(self):
        """Paints all waiting thumbnails smoothly without freezing the entire widget."""
        if not self.pending_thumbnails:
            return


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
                        
                        if "⏳" in item.text():
                            clean_name = os.path.basename(path)
                            item.setText(clean_name)
                except RuntimeError:
                    pass

        self.pending_thumbnails.clear()

    def on_scan_finished(self):
        if not self.loading_item_ref:
            return

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

        path = str(item.data(Qt.ItemDataRole.UserRole))
        is_currently_flat = item.data(Qt.ItemDataRole.UserRole + 4)

        is_open = item.data(Qt.ItemDataRole.UserRole + 30)
        item.setData(not is_open, Qt.ItemDataRole.UserRole + 30)

        if path.startswith("VIRTUAL_"):
            if is_open:
                self.ui.tree_view.expand(index)
            else:
                self.ui.tree_view.collapse(index)
            self.ui.tree_view.viewport().update()
            return

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
        if getattr(self, 'last_mouse_button', Qt.MouseButton.NoButton) == Qt.MouseButton.RightButton:
            return
        item = self.get_source_item(index)
        if not item: return
        path = str(item.data(Qt.ItemDataRole.UserRole))
        is_folder = item.data(Qt.ItemDataRole.UserRole + 2)
        is_flattened = item.data(Qt.ItemDataRole.UserRole + 4)

        if is_folder:
            if not self.ui.tree_view.isExpanded(index): self.ui.tree_view.expand(index)
            
            if path.startswith("VIRTUAL_"):
                return
                
            if not is_flattened: self.update_gallery_from_path(path)
        else:
            self.load_media(path)
            parent = item.parent()
            if parent and not parent.data(Qt.ItemDataRole.UserRole + 4):
                 parent_path = str(parent.data(Qt.ItemDataRole.UserRole))
                 
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

        if self.current_gallery_folder == folder_path:
            self.update_gallery_from_path(folder_path, force=True)

        def search_and_refresh(parent_item):
            for i in range(parent_item.rowCount()):
                child = parent_item.child(i)
                if not child: continue
                
                if child.data(Qt.ItemDataRole.UserRole) == folder_path:
                    if child.data(Qt.ItemDataRole.UserRole + 4): 
                        self.start_flattening(child, folder_path)
                    else:
                        self.populate_normal(child, folder_path)
                    return True
                
                if child.data(Qt.ItemDataRole.UserRole + 2):
                    if search_and_refresh(child):
                        return True
            return False

        search_and_refresh(self.model.invisibleRootItem())

    def load_media(self, path):
        if not path: return
        
        if hasattr(self, 'clear_player_timer') and self.clear_player_timer.isActive():
            self.clear_player_timer.stop()
            
        if path.startswith("custom_manga:"):
            self.current_image_path = None
            self.show_custom_manga(path)
            return
            
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

    def show_custom_manga(self, path):
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
        
        manga_id = int(path.split("|")[0].replace("custom_manga:", ""))
        paths = []
        try:
            conn = sqlite3.connect(self.current_db_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()
            cursor.execute("SELECT image_path FROM CustomMangaPages WHERE manga_id = ? ORDER BY page_number ASC", (manga_id,))
            paths = [row[0].strip() for row in cursor.fetchall()]
            conn.close()
        except Exception as e:
            print(f"Exception in show_custom_manga: {e}")
            
        print(f"DEBUG: Loaded {len(paths)} pages for manga_id {manga_id}")
            
        if hasattr(self.ui, 'manga_reader'):
            self.ui.manga_reader.show()
            self.ui.manga_reader.load_pages(paths)

    def show_image(self, path):
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.ui.video_container.hide() 
        self.ui.lbl_placeholder.hide()
        
        if hasattr(self, "thumb_worker"):
            self.thumb_worker.resume()
        if hasattr(self, "vid_thumb_worker") and hasattr(self.vid_thumb_worker, "resume"):
            self.vid_thumb_worker.resume()
        
        self.ui.image_view_container.show()

        self.ui.lbl_image.clear()

        movie = self.ui.lbl_image.movie()
        if movie:
            movie.stop()
            self.ui.lbl_image.setMovie(None)
            movie.deleteLater()

        if hasattr(self.ui, 'manga_reader'):
            self.ui.manga_reader.hide()

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
            
            self.ui.lbl_image.setMovie(movie)
            movie.start()
            if hasattr(self.ui.lbl_image, "_scale_content"):
                self.ui.lbl_image._scale_content()
            return

        reader = QImageReader(path)
        orig_size = reader.size()
        aspect_ratio = orig_size.height() / max(orig_size.width(), 1) if orig_size.isValid() else 1.0

        if aspect_ratio > 2.5:
            self.ui.lbl_image.hide()
            self.ui.manhwa_reader.show()
            self.ui.manhwa_zoom_slider.blockSignals(True)
            self.ui.manhwa_zoom_slider.setValue(100)
            self.ui.manhwa_zoom_slider.blockSignals(False)
            self.ui.manhwa_zoom_slider.show()

            try: 
                self.ui.manhwa_zoom_slider.valueChanged.disconnect()
            except TypeError: 
                pass 
            self.ui.manhwa_zoom_slider.valueChanged.connect(self.zoom_virtual_manhwa)

            folder_path = os.path.dirname(path)
            self.ui.manhwa_reader.load_folder(folder_path, jump_to_path=path)

        else:
            self.ui.manhwa_reader.hide()
            self.ui.lbl_image.show()
            self.ui.manhwa_zoom_slider.hide()

            MAX_CACHE = 50
            if path in self.image_cache:
                pixmap = self.image_cache[path]
            else:
                try:
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

            if not pixmap.isNull():
                if hasattr(self.ui.lbl_image, "set_raw_pixmap"):
                    self.ui.lbl_image.set_raw_pixmap(pixmap)
                else:
                    self.ui.lbl_image.setPixmap(pixmap)

    def zoom_virtual_manhwa(self, percentage):
        """Passes the slider zoom percentage into the high-performance reader."""
        if hasattr(self.ui, 'manhwa_reader'):
            self.ui.manhwa_reader.set_zoom(percentage)

    def zoom_manhwa(self, zoom_percentage):
        """Dynamically rescales the Manhwa image based on the slider percentage."""
        if not getattr(self, 'current_manhwa_pixmap', None):
            return

        new_width = int(self.manhwa_base_width * (zoom_percentage / 100.0))

        scaled_pixmap = self.current_manhwa_pixmap.scaledToWidth(new_width, Qt.TransformationMode.SmoothTransformation)
        self.ui.lbl_image.setPixmap(scaled_pixmap)

    def check_video_resolution(self, path):
        try:
            import cv2 as _cv2
            cap = _cv2.VideoCapture(path)
            if not cap.isOpened():
                return 0, 0
            w = int(cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            return w, h
        except Exception:
            return 0, 0



    def play_video(self, path):
        if not path:
            return

        perf_mode = getattr(self, "current_perf_mode", "balanced")
        
        self.ui.video_widget.show()

        if getattr(self, "current_perf_mode", "balanced") != "high":
            if hasattr(self, "thumb_worker"):
                self.thumb_worker.pause()
            if hasattr(self, "vid_thumb_worker"):
                try:
                    self.vid_thumb_worker.pause()
                except AttributeError:
                    pass

        self.ui.image_view_container.hide()
        self.ui.lbl_placeholder.hide()

        self.ui.video_container.show()

        self.media_player.stop()

        # Signal media_status_changed to auto-play once media is ready
        self._autoplay_pending = True

        self.media_player.setSource(QUrl.fromLocalFile(path))

        self.media_player.setPlaybackRate(1.0)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            self.play_previous()
            event.accept()
            return

        elif event.key() == Qt.Key.Key_Right:
            self.play_next()
            event.accept()
            return

        elif event.key() == Qt.Key.Key_Space:
            if self.ui.video_container.isVisible():
                self.toggle_play_pause()
            event.accept()
            return

        super().keyPressEvent(event)

    def on_gallery_item_changed(self, current_item, previous_item):
        if getattr(self, 'last_mouse_button', Qt.MouseButton.NoButton) == Qt.MouseButton.RightButton:
            return
        if current_item:
            path = current_item.data(Qt.ItemDataRole.UserRole)
            self.load_media(path)
            
            if getattr(self, 'db_connection', None):
                if hasattr(self, 'tag_fetch_worker') and self.tag_fetch_worker.isRunning():
                    self.tag_fetch_worker.stop()
                    self.tag_fetch_worker.wait()
                
                self.tag_fetch_worker = TagFetchWorker(self.current_db_path, path)
                self.tag_fetch_worker.tags_fetched.connect(self.on_tags_fetched)
                self.tag_fetch_worker.start()
            else:
                # No DB — hide the bottom stack if we're on the Tags page
                if self.ui.bottom_stack.currentIndex() == 0:
                    self.ui.bottom_stack.hide()
                    sizes = self.ui.sidebar_vertical_splitter.sizes()
                    total = sum(sizes)
                    self.ui.sidebar_vertical_splitter.setSizes([total, 0])

    def on_tags_fetched(self, tags):
        self.ui.tag_list_widget.clear()
        if tags:
            # Only switch to tags if file-info is NOT currently showing
            if self.ui.bottom_stack.currentIndex() != 1:
                self.ui.show_tags_in_stack()
            else:
                # Tags updated silently; populate but don't steal the view
                pass
            self.ui.tag_viewer_container.show()   # keep internal visibility flag correct
            for tag in tags:
                item = QListWidgetItem(tag)
                self.ui.tag_list_widget.addItem(item)
            # Make the bottom stack/tags visible
            self.ui.show_tags_in_stack()
        else:
            # No tags — if file-info isn't showing, collapse the bottom section
            if self.ui.bottom_stack.currentIndex() == 0:
                self.ui.bottom_stack.hide()
                sizes = self.ui.sidebar_vertical_splitter.sizes()
                total = sum(sizes)
                self.ui.sidebar_vertical_splitter.setSizes([total, 0])

    def add_main_tag(self):
        new_tag = self.ui.input_new_tag.text().strip().lower().replace(" ", "_")
        if not new_tag: return
        self.ui.input_new_tag.clear()

        current_item = self.ui.gallery_section.list_widget.currentItem()
        if not current_item: return
        path = current_item.data(Qt.ItemDataRole.UserRole)
        is_custom_manga = path.startswith("custom_manga:")

        try:
            conn = sqlite3.connect(self.current_db_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()

            cursor.execute("INSERT OR IGNORE INTO Tags (tag_name) VALUES (?)", (new_tag,))
            cursor.execute("SELECT tag_id FROM Tags WHERE tag_name = ?", (new_tag,))
            tag_id_row = cursor.fetchone()
            if not tag_id_row: return
            tag_id = tag_id_row[0]

            if is_custom_manga:
                manga_id = int(path.split("|")[0].replace("custom_manga:", ""))
                cursor.execute("INSERT OR IGNORE INTO CustomMangaTags (manga_id, tag_name) VALUES (?, ?)", (manga_id, new_tag))
            elif os.path.isdir(path):
                cursor.execute("SELECT gallery_id FROM MangaGalleries WHERE folder_path = ?", (path,))
                gallery_row = cursor.fetchone()
                if gallery_row:
                    cursor.execute("INSERT OR IGNORE INTO MangaTags (gallery_id, tag_id) VALUES (?, ?)", (gallery_row[0], tag_id))
            else:
                cursor.execute("SELECT hash FROM Images WHERE file_path = ?", (path,))
                img_row = cursor.fetchone()
                if img_row:
                    cursor.execute("INSERT OR IGNORE INTO ImageTags (hash, tag_id) VALUES (?, ?)", (img_row[0], tag_id))

            conn.commit()
            conn.close()

            item = QListWidgetItem(new_tag)
            self.ui.tag_list_widget.addItem(item)
            self.ui.show_tags_in_stack()
        except Exception as e:
            print(f"Error adding tag: {e}")

    def delete_main_tag(self):
        selected_items = self.ui.tag_list_widget.selectedItems()
        if not selected_items: return

        current_item = self.ui.gallery_section.list_widget.currentItem()
        if not current_item: return
        path = current_item.data(Qt.ItemDataRole.UserRole)
        is_custom_manga = path.startswith("custom_manga:")

        try:
            conn = sqlite3.connect(self.current_db_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()

            for item in selected_items:
                tag_name = item.text()
                
                if is_custom_manga:
                    manga_id = int(path.split("|")[0].replace("custom_manga:", ""))
                    cursor.execute("DELETE FROM CustomMangaTags WHERE manga_id = ? AND tag_name = ?", (manga_id, tag_name))
                else:
                    cursor.execute("SELECT tag_id FROM Tags WHERE tag_name = ?", (tag_name,))
                    tag_id_row = cursor.fetchone()
                    if tag_id_row:
                        tag_id = tag_id_row[0]
                        if os.path.isdir(path):
                            cursor.execute("SELECT gallery_id FROM MangaGalleries WHERE folder_path = ?", (path,))
                            gallery_row = cursor.fetchone()
                            if gallery_row:
                                cursor.execute("DELETE FROM MangaTags WHERE gallery_id = ? AND tag_id = ?", (gallery_row[0], tag_id))
                        else:
                            cursor.execute("SELECT hash FROM Images WHERE file_path = ?", (path,))
                            img_row = cursor.fetchone()
                            if img_row:
                                cursor.execute("DELETE FROM ImageTags WHERE hash = ? AND tag_id = ?", (img_row[0], tag_id))

            conn.commit()
            conn.close()

            for item in selected_items:
                row = self.ui.tag_list_widget.row(item)
                self.ui.tag_list_widget.takeItem(row)

        except Exception as e:
            print(f"Error deleting tag: {e}")

    def show_tag_context_menu(self, pos):
        item = self.ui.tag_list_widget.itemAt(pos)
        if not item: return

        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self.ui.tag_list_widget)
        
        edit_action = menu.addAction("Edit")
        delete_action = menu.addAction("Delete")
        
        menu.setStyleSheet("""
            QMenu { background-color: #252526; color: #d4d4d4; border: 1px solid #3e3e42; }
            QMenu::item { padding: 4px 20px; }
            QMenu::item:selected { background-color: #007acc; }
        """)

        action = menu.exec(self.ui.tag_list_widget.mapToGlobal(pos))
        if action == delete_action:
            self.ui.tag_list_widget.clearSelection()
            item.setSelected(True)
            self.delete_main_tag()
        elif action == edit_action:
            self.edit_main_tag(item)

    def edit_main_tag(self, item):
        from PyQt6.QtWidgets import QInputDialog
        old_tag = item.text()
        new_tag, ok = QInputDialog.getText(self, "Edit Tag", "Enter new tag name:", text=old_tag)
        if ok and new_tag.strip() and new_tag.strip() != old_tag:
            self.ui.tag_list_widget.clearSelection()
            item.setSelected(True)
            self.delete_main_tag()
            self.ui.input_new_tag.setText(new_tag.strip())
            self.add_main_tag()


    def on_search_bar_typed(self, text):
        self.search_timer.start()

    def force_instant_search(self):
        self.search_timer.stop()
        self.process_search()

    def on_gallery_scroll(self, value):
        if not getattr(self, 'db_connection', None):
            return
            
        search_text = self.ui.search_bar.text().strip().lower()
        if not search_text:
            return

        scrollbar = self.ui.gallery_section.list_widget.verticalScrollBar()
        
        if getattr(self, 'is_fetching_data', False):
            return
            
        if value >= scrollbar.maximum() - 100:
            self.is_fetching_data = True
            
            self.ui.lbl_placeholder.setText("⏳ Loading more...")
            self.ui.lbl_placeholder.show()
            filter_type = self.ui.gallery_section.filter_combo.currentText() if hasattr(self.ui.gallery_section, 'filter_combo') else "All"
            
            perf_mode = getattr(self, "current_perf_mode", "balanced")
            if perf_mode == "high":
                scroll_limit = 200
            elif perf_mode == "low":
                scroll_limit = 50
            else:
                scroll_limit = 100

            if hasattr(self.ui, 'loading_bar'):
                self.ui.loading_bar.show()
            self.db_search_worker = DatabaseSearchWorker(
                self.current_db_path, 
                search_text, 
                limit=scroll_limit, 
                offset=self.current_search_offset, 
                search_id=self.current_search_id,
                filter_type=filter_type
            )
            self.db_search_worker.search_finished.connect(self.on_db_search_finished)
            self.db_search_worker.error_occurred.connect(self.on_db_search_error)
            self.db_search_worker.start()
            
            self.current_search_offset += scroll_limit

    def process_search(self):
        text = self.ui.search_bar.text()
        search_text = text.strip().lower()
        
        self.clear_player_timer.start(200) 

        if getattr(self, 'db_connection', None) and hasattr(self, 'current_db_path'):
            
            if not self.ui.video_container.isVisible() and not self.ui.image_view_container.isVisible():
                self.ui.lbl_placeholder.setText("⏳ Searching...")
                self.ui.lbl_placeholder.show()

            if getattr(self, 'db_search_worker', None) and self.db_search_worker.isRunning():
                self.db_search_worker.stop()
                
                if not hasattr(self, 'zombie_workers'):
                    self.zombie_workers = []
                
                old_worker = self.db_search_worker
                self.zombie_workers.append(old_worker)
                
                old_worker.finished.connect(
                    lambda w=old_worker: self.zombie_workers.remove(w) if w in getattr(self, 'zombie_workers', []) else None
                )

            self.current_search_id += 1
            
            filter_type = self.ui.gallery_section.filter_combo.currentText() if hasattr(self.ui.gallery_section, 'filter_combo') else "All"

            perf_mode = getattr(self, "current_perf_mode", "balanced")
            if perf_mode == "high":
                initial_limit = 1000
            elif perf_mode == "low":
                initial_limit = 100
            else:
                initial_limit = 300
                
            self.current_search_offset = initial_limit 

            if hasattr(self.ui, 'loading_bar'):
                self.ui.loading_bar.show()
            self.db_search_worker = DatabaseSearchWorker(
                self.current_db_path, 
                search_text, 
                limit=initial_limit, 
                offset=0, 
                search_id=self.current_search_id,
                filter_type=filter_type
            )
            self.db_search_worker.search_finished.connect(self.on_db_search_finished)
            self.db_search_worker.error_occurred.connect(self.on_db_search_error)
            self.db_search_worker.start()
            return 
            
        self.proxy_model.set_search_text(search_text)


    def on_db_search_finished(self, results, folders_map, search_text, is_appending, search_id):
        if search_id != self.current_search_id:
            return 

        if hasattr(self.ui, 'loading_bar'):
            self.ui.loading_bar.hide()
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

        if not is_appending:
            self.ui.gallery_section.list_widget.clear()
            self.thumbnail_map.clear()
            self.thumb_worker.clear_queue()
            self.vid_thumb_worker.clear_queue()
            self.thumb_worker.resume()

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
                            
            search_root.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "search.svg"))))

        files_for_img_thumbs = []
        files_for_vid_thumbs = []

        scrollbar = self.ui.gallery_section.list_widget.verticalScrollBar()
        saved_scroll_pos = scrollbar.value()
        saved_row = self.ui.gallery_section.list_widget.currentRow()

        self.ui.gallery_section.list_widget.setUpdatesEnabled(False)

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

        self.ui.gallery_section.list_widget.setUpdatesEnabled(True)
        
        if is_appending:
            scrollbar.setValue(saved_scroll_pos)
            
            if saved_row >= 0:
                self.ui.gallery_section.list_widget.setCurrentRow(saved_row)
                
            self.ui.gallery_section.list_widget.setFocus()

        for folder_name, files in folders_map.items():
            existing_folder = None
            if search_root:
                for i in range(search_root.rowCount()):
                    if search_root.child(i).data(Qt.ItemDataRole.UserRole) == f"VIRTUAL_GROUP_{folder_name}":
                        existing_folder = search_root.child(i)
                        break
            
            if not existing_folder:
                existing_folder = QStandardItem(folder_name)
                
                existing_folder.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "folder.svg"))))
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

        self.is_fetching_data = False

    def on_db_search_error(self, error_msg):
        if hasattr(self.ui, 'loading_bar'):
            self.ui.loading_bar.hide()
        print(f"Database search error: {error_msg}")

    def render_search_batch(self):
        if getattr(self, 'cancel_search_rendering', False):
            return 
            
        items_to_render = 100
        rendered = 0
        
        files_for_img_thumbs = []
        files_for_vid_thumbs = []
        
        self.ui.gallery_section.list_widget.setUpdatesEnabled(False)

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
            
        self.ui.gallery_section.list_widget.setUpdatesEnabled(True)

        if self.search_render_folders and rendered < items_to_render:
            folder_name, files = self.search_render_folders.pop(0)
            folder_item = QStandardItem(f"{folder_name} ({len(files)} items)")
            
            folder_item.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "folder.svg"))))
            folder_item.setData(f"VIRTUAL_GROUP_{folder_name}", Qt.ItemDataRole.UserRole)
            folder_item.setData(True, Qt.ItemDataRole.UserRole + 2) 
            folder_item.setData(True, Qt.ItemDataRole.UserRole + 4) 
            
            for f_path, f_name, media_type in files:
                is_vid = media_type == "video" or (media_type == "image" and any(f_name.lower().endswith(e) for e in self.clean_vid_exts))
                file_item = self.create_file_item(f_name, f_path, is_vid)
                folder_item.appendRow(file_item)
                
            self.search_render_root.appendRow(folder_item)
            rendered += len(files) 

        if files_for_img_thumbs: self.thumb_worker.add_to_queue(files_for_img_thumbs)
        if files_for_vid_thumbs: self.vid_thumb_worker.add_to_queue(files_for_vid_thumbs)

        if self.search_render_results or self.search_render_folders:
            left = len(self.search_render_results)
            self.ui.lbl_placeholder.setText(f"⏳ Rendering... {left} remaining")
            
            QTimer.singleShot(5, self.render_search_batch)
        else:
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
        active_icon = QIcon(os.path.join(self.asset_dir, "svg2", f"{icon_name}.svg"))
        default_icon = QIcon(os.path.join(self.asset_dir, "svg", f"{icon_name}.svg"))

        button.setIcon(active_icon)
        QTimer.singleShot(duration, lambda: button.setIcon(default_icon))  


    def auto_load_database(self):
        
        if self.ui.btn_load_db.text().strip() == "DB ACTIVE":
            if getattr(self, 'db_connection', None):
                try:
                    self.db_connection.close()
                except Exception:
                    pass
                self.db_connection = None

            self.ui.btn_load_db.setText(" LOAD DB")
            self.ui.btn_load_db.setStyleSheet("""
                QPushButton {
                    background-color: #238636;
                    color: white;
                    border-radius: 10px; 
                    font-weight: bold;
                    font-size: 1.1em;     
                    padding: 0px 20px;   
                }
                QPushButton:hover { background-color: #2ea043; }
            """)
            
            self.ui.gallery_section.list_widget.clear()
            self.model.clear()
            self.model.setHorizontalHeaderLabels(["Name"])
            self.ui.search_bar.clear()
            
            if hasattr(self, 'tag_completer'):
                self.tag_completer.model().setStringList([])
                
            self.clear_media_viewer()
                
            print("Database disconnected cleanly.")
            return
            
        settings = QSettings("MediaNest", "AppConfig")
        db_folder = settings.value("db_folder_path", "", type=str)
        
        if not db_folder or not os.path.exists(db_folder):
            setup_window = FirstTimeSetupDialog(self)
            
            if setup_window.exec() == QDialog.DialogCode.Accepted:
                db_folder = settings.value("db_folder_path", "", type=str)
            else:
                return

        db_path = os.path.join(db_folder, "library.db")
        if os.path.exists(db_path):
            self.connect_to_database(db_path)
        else:
            QMessageBox.critical(self, "Error", f"Could not find library.db in:\n{db_folder}")

    def _get_categorized_tags(self):
        if not hasattr(self, 'db_connection'):
            return []
            
        cursor = self.db_connection.cursor()
        tag_dict = {}
        
        def add_tag(name, ns):
            prio = {'character': 5, 'artist': 4, 'series': 3, 'metadata': 2, 'general': 1}
            current_ns = tag_dict.get(name, 'general')
            if name not in tag_dict or prio.get(ns, 1) > prio.get(current_ns, 1):
                tag_dict[name] = ns
        
        try:
            cursor.execute("SELECT tag_name, tag_type FROM Tags")
            for row in cursor.fetchall():
                if row[0]:
                    add_tag(row[0], row[1] if row[1] else 'general')
        except sqlite3.OperationalError:
            cursor.execute("SELECT tag_name FROM Tags")
            for row in cursor.fetchall():
                if row[0]: add_tag(row[0], 'general')
                
        try:
            cursor.execute("SELECT DISTINCT artist FROM MangaGalleries WHERE artist IS NOT NULL AND artist != ''")
            for row in cursor.fetchall():
                if row[0]: add_tag(row[0], 'artist')
        except sqlite3.OperationalError:
            pass
            
        try:
            cursor.execute("SELECT DISTINCT tag_name FROM CustomMangaTags")
            for row in cursor.fetchall():
                if row[0]: add_tag(row[0], 'general')
            
            cursor.execute("SELECT DISTINCT title FROM CustomMangas WHERE title IS NOT NULL AND title != ''")
            for row in cursor.fetchall():
                if row[0]: add_tag(row[0], 'series')
        except sqlite3.OperationalError:
            pass
            
        def sort_key(item):
            name, ns = item
            ns_prio = {'character': 1, 'series': 2, 'artist': 3, 'metadata': 4, 'general': 5}
            return (ns_prio.get(ns, 99), name)
            
        return [f"{ns}:{name}" for name, ns in sorted(tag_dict.items(), key=sort_key)]

    def reload_autocomplete_tags(self):
        """Reloads all tags from the database and updates the completers (called when new custom mangas are created)."""
        all_tags = self._get_categorized_tags()
        
        if hasattr(self, 'tag_completer'):
            self.tag_completer._all_tags = all_tags
            self.tag_completer.model().setStringList(all_tags)
            
        try:
            if hasattr(self, 'settings_dialog') and hasattr(self.settings_dialog, 'tab_pagination'):
                if hasattr(self.settings_dialog.tab_pagination, 'tag_completer'):
                    self.settings_dialog.tab_pagination.tag_completer.model().setStringList(all_tags)
                if hasattr(self.settings_dialog.tab_pagination, 'custom_tags_completer'):
                    self.settings_dialog.tab_pagination.custom_tags_completer.model().setStringList(all_tags)
        except Exception:
            pass

    def _install_ns_tab_filter(self, widget):
        expander = NsTabExpander(widget, parent=self)
        widget.installEventFilter(expander)
        if not hasattr(self, '_ns_tab_filters'):
            self._ns_tab_filters = []
        self._ns_tab_filters.append(expander)

    def upgrade_legacy_tags(self):
        try:
            cursor = self.db_connection.cursor()
            try:
                cursor.execute("ALTER TABLE Tags ADD COLUMN tag_type TEXT DEFAULT 'general'")
                self.db_connection.commit()
                print("Added 'tag_type' column to Tags table.")
            except sqlite3.OperationalError:
                pass 

            cursor.execute("""
                SELECT DISTINCT tag_name FROM Tags
                WHERE tag_type IS NULL OR tag_type = '' OR tag_type = 'general'
            """)
            unresolved_tags = set(row[0] for row in cursor.fetchall() if row[0])
            if not unresolved_tags:
                return

            db_folder = os.path.dirname(self.current_db_path)
            alltags_db_path = os.path.join(db_folder, "AllTags.db")
            if not os.path.exists(alltags_db_path):
                return

            all_conn = sqlite3.connect(alltags_db_path)
            all_conn.execute("PRAGMA journal_mode=WAL;")
            all_cursor = all_conn.cursor()

            tables_to_ns = {
                'CharacterTags': 'character',
                'SeriesTags': 'series',
                'ArtistTags': 'artist',
                'MetadataTags': 'metadata'
            }

            updates_made = 0
            for table, ns in tables_to_ns.items():
                if not unresolved_tags:
                    break

                tags_list = list(unresolved_tags)
                chunk_size = 900
                found_in_table = set()

                for i in range(0, len(tags_list), chunk_size):
                    chunk = tags_list[i:i + chunk_size]
                    placeholders = ",".join("?" * len(chunk))
                    try:
                        all_cursor.execute(
                            f"SELECT name FROM {table} WHERE name IN ({placeholders})", chunk
                        )
                        for row in all_cursor.fetchall():
                            tag = row[0]
                            cursor.execute(
                                "UPDATE Tags SET tag_type = ? WHERE tag_name = ?", (ns, tag)
                            )
                            updates_made += 1
                            found_in_table.add(tag)
                    except sqlite3.OperationalError:
                        pass

                unresolved_tags -= found_in_table

            if updates_made > 0:
                self.db_connection.commit()
                print(f"Upgraded {updates_made} tags to their correct namespaces in library.db.")

            all_conn.close()
        except Exception as e:
            print(f"WARN: Failed to upgrade legacy tags: {e}")

    def connect_to_database(self, db_path):
        """Establishes the SQLite connection and updates the UI."""
        try:
            self.current_db_path = db_path
            self.db_connection = sqlite3.connect(db_path, check_same_thread=False)
            self.db_connection.execute("PRAGMA journal_mode=WAL;")
            
            cursor = self.db_connection.cursor()
            
            cursor.execute("CREATE TABLE IF NOT EXISTS CustomMangas (manga_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, cover_image TEXT)")
            cursor.execute("CREATE TABLE IF NOT EXISTS CustomMangaPages (manga_id INTEGER, image_path TEXT, page_number INTEGER, PRIMARY KEY (manga_id, page_number))")
            cursor.execute("CREATE TABLE IF NOT EXISTS CustomMangaTags (manga_id INTEGER, tag_name TEXT, PRIMARY KEY (manga_id, tag_name))")
            
            # Migrate Images table
            try:
                cursor.execute("ALTER TABLE Images ADD COLUMN file_size INTEGER")
                print("Added 'file_size' column to Images table.")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Migrate tagless table
            try:
                cursor.execute("ALTER TABLE tagless ADD COLUMN file_size INTEGER")
                print("Added 'file_size' column to tagless table.")
            except sqlite3.OperationalError:
                pass  # Column already exists

            self.db_connection.commit()
            
            self.upgrade_legacy_tags()
            
            # Start background backfill worker for file sizes
            if not hasattr(self, 'file_size_worker') or not self.file_size_worker.isRunning():
                self.file_size_worker = FileSizeBackfillWorker(db_path)
                self.file_size_worker.start()
                
            all_tags = self._get_categorized_tags()
            
            self.tag_completer = MultiTagCompleter(all_tags, self)
            self.tag_completer.model().setStringList(all_tags)
            
            try:
                current_scale = float(os.environ.get("QT_SCALE_FACTOR", "1.0"))
                if current_scale < 1.0:
                    font_style = "font-size: 1.1em; font-weight: bold;"
                else:
                    font_style = "font-size: 1em; font-weight: normal;"
            except Exception:
                font_style = "font-size: 1em; font-weight: normal;"

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
            
            self.ui.search_bar.setCompleter(self.tag_completer)
            self._install_ns_tab_filter(self.ui.search_bar)

            self.ui.btn_load_db.setText(" DB ACTIVE")
            self.ui.btn_load_db.setStyleSheet("""
                QPushButton {
                    background-color: #8957e5;
                    color: white;
                    border-radius: 10px; 
                    font-weight: bold;
                    font-size: 1.1em;  
                    padding: 0px 20px;  
                }
            """)
            print(f"Successfully connected to database at: {db_path}")
            print(f"Loaded {len(all_tags)} unique tags into the autocomplete engine.")
            
        except Exception as e:
            print(f"Failed to load database: {e}")
            self.db_connection = None