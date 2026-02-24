import sys
import os
from PyQt6.QtWidgets import (QMainWindow, QFileDialog, QApplication, QMenu, 
                             QStyledItemDelegate, QStyle, QListWidgetItem)
from PyQt6.QtGui import (QPixmap, QIcon, QAction, QStandardItemModel, 
                         QStandardItem, QColor, QPainter, QImageReader, QImage)
from PyQt6.QtCore import (QDir, QUrl, Qt, QRect, QEvent, pyqtSignal, QTimer, 
                          QThread, QObject, QSize, QSortFilterProxyModel)

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

from Src.Ui.interface import MainWindowUI
from Src.Ui.theme import VSCODE_DARK_THEME

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
        self.timeout_timer.stop()
        self.is_processing = False
        self.current_path = None

    def process_next(self):
        if not self.queue:
            self.is_processing = False
            self.current_path = None
            return
        
        self.is_processing = True
        self.current_path = self.queue.pop(0)
        
        self.player.setSource(QUrl.fromLocalFile(self.current_path))
        self.player.play()
        self.timeout_timer.start(3000) 

    def on_frame_changed(self, frame):
        if not self.is_processing or not self.current_path:
            return
            
        image = frame.toImage()
        if image.isNull():
            return
            
        self.timeout_timer.stop()
        self.player.stop()
        
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
        self.current_path = None
        self.process_next()

# --- IMAGE THUMBNAIL WORKER ---
class ThumbnailWorker(QThread):
    thumbnail_ready = pyqtSignal(str, QImage)

    def __init__(self):
        super().__init__()
        self.queue = []
        self.is_running = True

    def add_to_queue(self, path_list):
        self.queue.extend(path_list)
        if not self.isRunning():
            self.start()

    def clear_queue(self):
        self.queue.clear()

    def run(self):
        while self.is_running:
            if not self.queue:
                self.msleep(100) 
                continue

            path = self.queue.pop(0)
            TARGET_SIZE = 220 
            
            reader = QImageReader(path)
            orig_size = reader.size()
            
            if orig_size.isValid():
                ratio = min(TARGET_SIZE / orig_size.width(), TARGET_SIZE / orig_size.height())
                new_w = int(orig_size.width() * ratio)
                new_h = int(orig_size.height() * ratio)
                reader.setScaledSize(QSize(new_w, new_h))
            
            loaded_image = reader.read()
            
            if not loaded_image.isNull():
                final_image = QImage(TARGET_SIZE, TARGET_SIZE, QImage.Format.Format_ARGB32)
                final_image.fill(Qt.GlobalColor.transparent)
                
                painter = QPainter(final_image)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                x_pos = (TARGET_SIZE - loaded_image.width()) // 2
                y_pos = (TARGET_SIZE - loaded_image.height()) // 2
                painter.drawImage(x_pos, y_pos, loaded_image)
                painter.end()
                
                self.thumbnail_ready.emit(path, final_image)
            
            self.msleep(5)

    def stop(self):
        self.is_running = False
        self.wait()

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

        # Always keep 'Loading...' visible so we don't break lazy-loaded folders
        if "loading..." in item_text:
            return True

        # RULE 1: Does this exact item match the search?
        if self.search_text in item_text:
            return True

        # RULE 2: Does any PARENT of this item match? 
        # (If user searched for a folder, show all files inside it)
        parent_idx = index.parent()
        while parent_idx.isValid():
            parent_item = source_model.itemFromIndex(parent_idx)
            if parent_item and self.search_text in parent_item.text().lower():
                return True
            parent_idx = parent_idx.parent()

        # RULE 3: Does any CHILD of this item match? 
        # (If user searched for a file, keep its parent folders visible)
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

        # If it fails all 3 rules, hide it!
        return False

# --- SCANNER WORKER ---
class ScannerWorker(QThread):
    batch_found = pyqtSignal(list)
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
                    rel_path = os.path.relpath(full_path, self.folder_path)
                    display_name = rel_path.replace("\\", " > ")
                    batch.append( (display_name, full_path, is_vid) )

                    if len(batch) >= 50: 
                        self.batch_found.emit(batch)
                        batch = []
                        self.msleep(10)

        if batch: self.batch_found.emit(batch)
        self.finished.emit()

    def stop(self):
        self.is_running = False

# --- DELEGATE ---
class FolderButtonDelegate(QStyledItemDelegate):
    button_clicked = pyqtSignal(object)
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        is_folder = index.data(Qt.ItemDataRole.UserRole + 2)
        has_subfolders = index.data(Qt.ItemDataRole.UserRole + 6)
        is_flat_root = index.data(Qt.ItemDataRole.UserRole + 4)

        if (is_folder and has_subfolders) or is_flat_root:
            button_rect = QRect(option.rect.right() - 30, option.rect.top(), 30, option.rect.height())
            painter.save()
            if option.state & QStyle.StateFlag.State_MouseOver: painter.setPen(QColor("#ffffff")) 
            else: painter.setPen(QColor("#888888"))
            emoji = "📂" if is_flat_root else "📁"
            font = painter.font(); font.setPointSize(11); painter.setFont(font)
            painter.drawText(button_rect, Qt.AlignmentFlag.AlignCenter, emoji)
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

# --- MAIN APP ---
class MediaExplorerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = MainWindowUI()
        self.image_cache = {}
        self.ui.setup_ui(self)
        self.setWindowTitle("Media Nest V1.0.0")
        self.setStyleSheet(VSCODE_DARK_THEME)

        logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "Logo.png"))
        self.setWindowIcon(QIcon(logo_path))

        self.image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp', '*.webp']
        self.video_extensions = ['*.mp4', '*.mkv', '*.avi', '*.mov', '*.webm']
        self.clean_img_exts = [e.replace("*", "") for e in self.image_extensions]
        self.clean_vid_exts = [e.replace("*", "") for e in self.video_extensions]

        self.setup_media_player()
        
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["Name"])

        self.proxy_model = SmartTreeFilter()
        self.proxy_model.setSourceModel(self.model)        
        self.ui.tree_view.setModel(self.proxy_model)
        
        # Wire up the search bar to fire instantly as you type
        self.ui.search_bar.textChanged.connect(self.on_search_bar_typed)

        self.delegate = FolderButtonDelegate(self.ui.tree_view)
        self.delegate.button_clicked.connect(self.on_folder_toggle)
        self.ui.tree_view.setItemDelegate(self.delegate)

        self.ui.btn_open.clicked.connect(self.open_folder_dialog)
        self.ui.tree_view.clicked.connect(self.on_tree_item_clicked)
        self.ui.tree_view.expanded.connect(self.on_item_expanded)
        self.ui.gallery_section.file_selected.connect(self.load_media)
        self.ui.gallery_section.list_widget.currentItemChanged.connect(self.on_gallery_item_changed)
        self.current_image_path = None
        self.current_gallery_folder = None 
        self.scanner_thread = None
        self.loading_item_ref = None 
        
        self.thumbnail_map = {} 
        self.thumb_worker = ThumbnailWorker()
        self.thumb_worker.thumbnail_ready.connect(self.on_thumbnail_ready)
        self.thumb_worker.start()
        
        self.vid_thumb_worker = VideoThumbnailer()
        self.vid_thumb_worker.thumbnail_ready.connect(self.on_thumbnail_ready)
        self.autohide_timer = QTimer(self)
        self.autohide_timer.setInterval(3000) # 3000 milliseconds = 3 seconds
        self.autohide_timer.timeout.connect(self.hide_fullscreen_controls)
        
        QApplication.instance().installEventFilter(self)        


    def resizeEvent(self, event):
        if self.current_image_path and self.ui.lbl_image.isVisible():
            self.show_image(self.current_image_path)
        super().resizeEvent(event)

    def setup_media_player(self):
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.ui.video_widget)

        # Hook up Play, Pause, and Skip buttons
        self.ui.btn_play.clicked.connect(self.toggle_play_pause)
        self.ui.btn_skip_backward.clicked.connect(self.skip_backward)
        self.ui.btn_skip_forward.clicked.connect(self.skip_forward)
        self.ui.btn_fullscreen.clicked.connect(self.toggle_fullscreen)        
        self.media_player.playbackStateChanged.connect(self.media_state_changed)
        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.durationChanged.connect(self.duration_changed)
        self.ui.slider_progress.sliderMoved.connect(self.set_position)

    def skip_backward(self):
        current_pos = self.media_player.position()
        self.media_player.setPosition(max(0, current_pos - 10000))

    def skip_forward(self):
        current_pos = self.media_player.position()
        duration = self.media_player.duration()
        if duration > 0:
            self.media_player.setPosition(min(duration, current_pos + 10000))

    def toggle_play_pause(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            # Restore normal view
            self.showNormal()
            self.ui.sidebar_widget.show()
            self.ui.gallery_section.show()
            self.ui.btn_fullscreen.setText("⛶")
            
            # Stop the timer, ensure controls are visible, and bring mouse back
            self.autohide_timer.stop()
            self.ui.video_controls.show()
            self.unsetCursor()
        else:
            # Enter fullscreen mode
            self.showFullScreen()
            self.ui.sidebar_widget.hide()
            self.ui.gallery_section.hide()
            self.ui.btn_fullscreen.setText("🗗") 
            
            # Start the 3-second auto-hide timer
            self.autohide_timer.start()

    def media_state_changed(self, state):
        self.ui.btn_play.setIcon(QIcon())
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.ui.btn_play.setText("⏸️")
        else:
            self.ui.btn_play.setText("▶️")

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
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["Name"])
        root_name = os.path.basename(path)
        root_item = self.create_folder_item(root_name, path)
        self.model.appendRow(root_item)
        self.populate_normal(root_item, path)
        
        # Safely map to the proxy to expand the root folder
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
        if has_any: item.appendRow(QStandardItem("Loading..."))
        return item

    def create_file_item(self, name, path, is_video):
        icon = "🎬" if is_video else "🖼️"
        item = QStandardItem(f"{icon} {name}")
        item.setData(path, Qt.ItemDataRole.UserRole)
        item.setData(False, Qt.ItemDataRole.UserRole + 2)
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
        # Smart check: If Qt gave us a proxy index, map it. If it's already a source index, just use it directly!
        if hasattr(self, 'proxy_model') and index.model() == self.proxy_model:
            source_index = self.proxy_model.mapToSource(index)
            return self.model.itemFromIndex(source_index)
        return self.model.itemFromIndex(index)    

    def on_item_expanded(self, index):
        item = self.get_source_item(index)
        
        # 1. Safety Check: If the item is null, skip it
        if not item: 
            return
            
        # 2. Safety Check: If we already loaded this or it's flattened, skip it
        if item.data(Qt.ItemDataRole.UserRole + 5) or item.data(Qt.ItemDataRole.UserRole + 4): 
            return
            
        path = item.data(Qt.ItemDataRole.UserRole)
        
        # --- NEW SAFETY GATE ---
        # Only try to populate if the path is actually a directory on your disk
        if os.path.isdir(path):
            self.populate_normal(item, path)
        else:
            # If it's a file, just mark it as 'loaded' so we don't try again
            item.setData(True, Qt.ItemDataRole.UserRole + 5)

    def eventFilter(self, obj, event):
        # If the mouse moves or is clicked anywhere in the app...
        if event.type() in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress):
            if self.isFullScreen():
                self.show_fullscreen_controls()
        return super().eventFilter(obj, event)

    def hide_fullscreen_controls(self):
        if self.isFullScreen():
            self.ui.video_controls.hide()
            self.setCursor(Qt.CursorShape.BlankCursor) # This hides the mouse pointer too!

    def show_fullscreen_controls(self):
        if self.isFullScreen():
            if self.ui.video_controls.isHidden():
                self.ui.video_controls.show()
                self.unsetCursor() # Brings the mouse pointer back
            
            # Restart the 3-second countdown every time the mouse moves
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
        
        if self.scanner_thread and self.scanner_thread.isRunning():
            self.scanner_thread.stop()
            self.scanner_thread.wait()

        self.loading_item_ref = parent_item
        self.scanner_thread = ScannerWorker(folder_path, self.clean_img_exts, self.clean_vid_exts)
        self.scanner_thread.batch_found.connect(self.on_batch_received)
        self.scanner_thread.finished.connect(self.on_scan_finished)
        self.scanner_thread.start()

    def on_batch_received(self, batch):
        parent_item = self.loading_item_ref
        if parent_item.rowCount() == 1 and parent_item.child(0).text() == "⏳ Scanning...":
            parent_item.removeRow(0)

        for display_name, full_path, is_vid in batch:
            parent_item.appendRow(self.create_file_item(display_name, full_path, is_vid))

        files_for_img_thumbs = []
        files_for_vid_thumbs = []
        
        for name, path, is_video in batch:
            clean_name = os.path.basename(name)
            item = QListWidgetItem(clean_name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setSizeHint(QSize(240, 260))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            
            icon_text = "🎬 ⏳" if is_video else "🖼️ ⏳"
            item.setText(f"{icon_text} {clean_name}") 
            
            if is_video:
                files_for_vid_thumbs.append(path)
            else:
                files_for_img_thumbs.append(path)
                
            self.thumbnail_map[path] = item 
            self.ui.gallery_section.list_widget.addItem(item)

        if files_for_img_thumbs: self.thumb_worker.add_to_queue(files_for_img_thumbs)
        if files_for_vid_thumbs: self.vid_thumb_worker.add_to_queue(files_for_vid_thumbs)

    def on_thumbnail_ready(self, path, qimage):
        if path in self.thumbnail_map:
            try:
                item = self.thumbnail_map[path]
                if self.ui.gallery_section.list_widget.row(item) != -1:
                    pixmap = QPixmap.fromImage(qimage)
                    item.setIcon(QIcon(pixmap))
                    
                    clean_name = os.path.basename(path)
                    icon_text = "🎬" if path.lower().endswith(tuple(self.clean_vid_exts)) else "🖼️"
                    item.setText(f"{icon_text} {clean_name}")
            except RuntimeError:
                pass 

    def on_scan_finished(self):
        if self.loading_item_ref:
            self.loading_item_ref.setData(True, Qt.ItemDataRole.UserRole + 5)
            if self.loading_item_ref.rowCount() == 1 and self.loading_item_ref.child(0).text() == "⏳ Scanning...":
                 self.loading_item_ref.removeRow(0)
                 self.loading_item_ref.appendRow(QStandardItem("No media found."))

    def on_folder_toggle(self, index):
        item = self.get_source_item(index)
        if not item: return
        path = item.data(Qt.ItemDataRole.UserRole)
        is_currently_flat = item.data(Qt.ItemDataRole.UserRole + 4)
        
        if is_currently_flat:
            if self.scanner_thread and self.scanner_thread.isRunning(): self.scanner_thread.stop()
            self.thumb_worker.clear_queue() 
            self.vid_thumb_worker.clear_queue()
            item.setData(False, Qt.ItemDataRole.UserRole + 4)
            self.populate_normal(item, path)
            self.update_gallery_from_path(path) 
        else:
            item.setData(True, Qt.ItemDataRole.UserRole + 4)
            self.start_flattening(item, path)
        self.ui.tree_view.expand(index)

    def on_tree_item_clicked(self, index):
        item = self.get_source_item(index)
        if not item: return
        path = item.data(Qt.ItemDataRole.UserRole)
        is_folder = item.data(Qt.ItemDataRole.UserRole + 2)
        is_flattened = item.data(Qt.ItemDataRole.UserRole + 4)

        if is_folder:
            if not self.ui.tree_view.isExpanded(index): self.ui.tree_view.expand(index)
            if not is_flattened: self.update_gallery_from_path(path)
        else:
            self.load_media(path)
            parent = item.parent()
            if parent and not parent.data(Qt.ItemDataRole.UserRole + 4):
                 parent_path = parent.data(Qt.ItemDataRole.UserRole)
                 self.update_gallery_from_path(parent_path)

    def update_gallery_from_path(self, folder_path):
        if self.current_gallery_folder == folder_path: return 
        self.current_gallery_folder = folder_path
        
        self.ui.gallery_section.list_widget.clear()
        self.thumbnail_map.clear()
        self.thumb_worker.clear_queue()
        self.vid_thumb_worker.clear_queue()
        
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
                        
                        icon_text = "🎬 ⏳" if is_vid else "🖼️ ⏳"
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

    def load_media(self, path):
        if not path: return
        name = path.lower()
        is_image = any(name.endswith(ext) for ext in self.clean_img_exts)
        is_video = any(name.endswith(ext) for ext in self.clean_vid_exts)
        if is_image:
            self.current_image_path = path
            self.show_image(path)
        elif is_video:
            self.current_image_path = None
            self.play_video(path)

    def show_image(self, path):
        self.media_player.stop()
        self.ui.video_container.hide() 
        self.ui.lbl_placeholder.hide()
        self.ui.scroll_area.show()

        MAX_CACHE = 50
        if path in self.image_cache:
            pixmap = self.image_cache[path]
        else:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.image_cache[path] = pixmap

                if len(self.image_cache) > MAX_CACHE:
                    self.image_cache.pop(next(iter(self.image_cache)))


        if not pixmap.isNull():
            avail_w = self.ui.scroll_area.width() - 20
            avail_h = self.ui.scroll_area.height() - 20
            if pixmap.width() > avail_w or pixmap.height() > avail_h:
                pixmap = pixmap.scaled(avail_w, avail_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.ui.lbl_image.setPixmap(pixmap)

    def play_video(self, path):
        self.ui.scroll_area.hide()
        self.ui.lbl_placeholder.hide()
        self.ui.video_container.show() 
        
        self.ui.lbl_title.setText(os.path.basename(path))
        
        self.media_player.setSource(QUrl.fromLocalFile(path))
        self.media_player.play()

    def keyPressEvent(self, event):
      
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
            return      
        list_widget = self.ui.gallery_section.list_widget
        
        # If the gallery is empty, don't do anything
        if list_widget.count() == 0:
            super().keyPressEvent(event)
            return

        current_row = list_widget.currentRow()
        new_row = current_row

        # Check which key was pressed
        if event.key() == Qt.Key.Key_Left:
            # Move left, but don't go below 0
            new_row = max(0, current_row - 1) if current_row > 0 else 0
            
        elif event.key() == Qt.Key.Key_Right:
            # If nothing is selected (-1), start at the first item (0)
            if current_row == -1:
                new_row = 0
            else:
                # Move right, but don't go past the last item
                new_row = min(list_widget.count() - 1, current_row + 1)
                
        else:
            # If it was any other key (like Space or Up/Down), let the app handle it normally
            super().keyPressEvent(event)
            return

        # If the row actually changed, update everything
        if new_row != current_row:
            # 1. Update the blue selection highlight in the gallery
            list_widget.setCurrentRow(new_row)
            item = list_widget.item(new_row)
            
            if item:
                # 2. Automatically scroll the gallery so the item doesn't go off-screen!
                list_widget.scrollToItem(item)
                
                # 3. Load the actual image or video into the main viewer
                path = item.data(Qt.ItemDataRole.UserRole)
                self.load_media(path)        

    def on_gallery_item_changed(self, current_item, previous_item):
        # When the user uses arrow keys, this native signal fires automatically
        if current_item:
            path = current_item.data(Qt.ItemDataRole.UserRole)
            self.load_media(path)                

    def on_search_bar_typed(self, text):
        search_text = text.strip()

        # Update tree filter
        self.proxy_model.set_search_text(search_text)

        if search_text:
            self.ui.tree_view.expandAll()
        else:
            self.ui.tree_view.collapseAll()
            root_index = self.proxy_model.index(0, 0)
            if root_index.isValid():
                self.ui.tree_view.expand(root_index)

        # ===============================
        # HARD RESET THUMBNAILS
        # ===============================
        # 1️⃣ Stop workers completely
        self.thumb_worker.stop()
        self.vid_thumb_worker.clear_queue()

        # 2️⃣ Recreate image worker fresh
        self.thumb_worker = ThumbnailWorker()
        self.thumb_worker.thumbnail_ready.connect(self.on_thumbnail_ready)
        self.thumb_worker.start()

        files_for_img_thumbs = []
        files_for_vid_thumbs = []

        list_widget = self.ui.gallery_section.list_widget
        search_text = search_text.lower()

        for i in range(list_widget.count()):
            item = list_widget.item(i)
            file_name = item.text().lower()
            path = item.data(Qt.ItemDataRole.UserRole)

            is_match = search_text in file_name
            item.setHidden(not is_match)

            if is_match:
                if path.lower().endswith(tuple(self.clean_vid_exts)):
                    files_for_vid_thumbs.append(path)
                else:
                    files_for_img_thumbs.append(path)

        # 3️⃣ Start loading only visible ones
        if files_for_img_thumbs:
            self.thumb_worker.add_to_queue(files_for_img_thumbs)

        if files_for_vid_thumbs:
            self.vid_thumb_worker.add_to_queue(files_for_vid_thumbs)