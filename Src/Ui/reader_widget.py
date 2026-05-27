# Src/Ui/reader_widget.py
import os
import bisect
import re
from collections import OrderedDict

from PyQt6.QtCore import Qt, QRect, QSize, QRunnable, QThreadPool, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QPainter, QPixmap, QColor, QImageReader
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel, QSizePolicy

def natural_key(text):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", text)]

class LoaderSignals(QObject):
    loaded = pyqtSignal(str, QPixmap, QSize)

class ImageLoader(QRunnable):
    def __init__(self, path, target_width, signals):
        super().__init__()
        self.path = path
        # We no longer aggressively shrink the image to the target_width
        self.target_width = target_width 
        self.signals = signals

    def run(self):
        # Read the raw, original high-res image
        reader = QImageReader(self.path)
        image = reader.read()
        
        if image.isNull():
            return

        # Keep it at 100% original quality in RAM!
        pixmap = QPixmap.fromImage(image)
        
        # 🔹 ANTI-CRASH FIX 🔹
        # Safely attempt to send the image to the UI. 
        # If the user closed the reader while we were loading, just ignore it!
        try:
            self.signals.loaded.emit(self.path, pixmap, pixmap.size())
        except RuntimeError:
            pass

class ManhwaReaderWidget(QWidget):
    BACKGROUND = QColor(30, 30, 30)
    PRELOAD_DISTANCE = 3
    MAX_CACHE_IMAGES = 25

    def __init__(self, scroll_area):
        super().__init__()
        self.scroll_area = scroll_area
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

        self.paths = []
        self.page_heights = []
        self.page_offsets = []
        self.estimated_height = 1600
        self.cache = OrderedDict()
        self.loading = set()
        
        self.thread_pool = QThreadPool.globalInstance()
        self.signals = LoaderSignals()
        self.signals.loaded.connect(self.on_image_loaded)
        
        # --- ZOOM VARIABLES ---
        self.zoom_factor = 1.0
        self.viewport_width = 1000
        self.current_target_width = 1000
        self.setMinimumWidth(self.viewport_width)

    def set_zoom(self, percentage):
        self.zoom_factor = percentage / 100.0
        
        # Calculate new width based on visible screen space
        visible_width = self.scroll_area.viewport().width()
        self.current_target_width = int(visible_width * self.zoom_factor)
        
        # Force widget to grow horizontally if zoomed in > 100%
        self.setMinimumWidth(max(visible_width, self.current_target_width))
        
        # Reset heights to smooth out the transition
        self.page_heights = [self.estimated_height for _ in self.paths]
        self.recalculate_offsets()
        
        self.cache.clear()
        self.loading.clear()
        self.update()
        self.load_visible_images()

    def load_folder(self, folder, jump_to_path=None):
        exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
        files = [
            os.path.join(folder, f) for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in exts
        ]
        files.sort(key=lambda p: natural_key(os.path.basename(p)))
        
        self.paths = files
        self.page_heights = [self.estimated_height for _ in self.paths]
        self.recalculate_offsets()
        self.cache.clear()
        self.loading.clear()
        
        self.update()
        self.load_visible_images()

        # Jump to specific image if clicked from the gallery!
        if jump_to_path and jump_to_path in self.paths:
            idx = self.paths.index(jump_to_path)
            target_y = self.page_offsets[idx]
            self.scroll_area.verticalScrollBar().setValue(target_y)

    def recalculate_offsets(self):
        self.page_offsets = []
        y = 0
        for h in self.page_heights:
            self.page_offsets.append(y)
            y += h
        self.total_height = y
        self.setMinimumHeight(self.total_height)

    def on_image_loaded(self, path, pixmap, size):
        if path not in self.paths: return
        index = self.paths.index(path)
        
        self.cache[path] = pixmap
        self.cache.move_to_end(path)
        while len(self.cache) > self.MAX_CACHE_IMAGES:
            self.cache.popitem(last=False)
            
        # 🔹 ASPECT RATIO FIX 🔹
        # Calculate the exact ratio between the original width and your screen's target width
        orig_w = size.width()
        orig_h = size.height()
        
        if orig_w > 0:
            ratio = self.current_target_width / orig_w
            scaled_height = int(orig_h * ratio)
        else:
            scaled_height = orig_h
            
        # Apply the scaled height instead of the raw original height
        old_height = self.page_heights[index]
        if old_height != scaled_height:
            self.page_heights[index] = scaled_height
            self.recalculate_offsets()
            
        self.loading.discard(path)
        self.update()

    def visible_range(self):
        scroll = self.scroll_area.verticalScrollBar().value()
        viewport_h = self.scroll_area.viewport().height()
        
        start = bisect.bisect_left(self.page_offsets, scroll)
        end = bisect.bisect_right(self.page_offsets, scroll + viewport_h)
        
        start = max(0, start - self.PRELOAD_DISTANCE)
        end = min(len(self.paths), end + self.PRELOAD_DISTANCE)
        return start, end

    def load_visible_images(self):
        if not self.paths: return
        start, end = self.visible_range()
        for i in range(start, end):
            path = self.paths[i]
            if path in self.cache or path in self.loading: continue
            
            self.loading.add(path)
            # Use current_target_width instead of viewport_width
            worker = ImageLoader(path, self.current_target_width, self.signals)
            self.thread_pool.start(worker)

    def scroll_update(self):
        self.load_visible_images()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        
        # 🔹 Turn on High-Quality Anti-Aliasing for rendering!
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        painter.fillRect(self.rect(), self.BACKGROUND)
        
        rect = event.rect()
        start = bisect.bisect_left(self.page_offsets, rect.top())
        end = bisect.bisect_right(self.page_offsets, rect.bottom())
        start = max(0, start - 1)
        end = min(len(self.paths), end + 1)
        
        x_offset = max(0, (self.width() - self.current_target_width) // 2)
        
        for i in range(start, end):
            y = self.page_offsets[i]
            path = self.paths[i]
            if path in self.cache:
                # 🔹 Tell the painter to dynamically draw the massive image into the smaller screen space
                target_rect = QRect(x_offset, y, self.current_target_width, self.page_heights[i])
                painter.drawPixmap(target_rect, self.cache[path])
            else:
                painter.fillRect(QRect(x_offset, y, self.current_target_width, self.page_heights[i]), QColor(20, 20, 20))
                
        painter.end()

    def resizeEvent(self, event):
        visible_width = self.scroll_area.viewport().width()
        if visible_width != self.viewport_width and visible_width > 0:
            self.viewport_width = visible_width
            self.current_target_width = int(self.viewport_width * self.zoom_factor)
            self.setMinimumWidth(max(self.viewport_width, self.current_target_width))
            
            self.cache.clear()
            self.loading.clear()
            self.page_heights = [self.estimated_height for _ in self.paths]
            self.recalculate_offsets()
            self.load_visible_images()
        super().resizeEvent(event)

class ReaderImageLabel(QLabel):
    clicked_left = pyqtSignal()
    clicked_right = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.is_zoomed = False
        self._raw_pixmap = None
        self._single_click_timer = QTimer()
        self._single_click_timer.setSingleShot(True)
        self._single_click_timer.timeout.connect(self._on_single_click)
        self._last_click_pos = None
        self.update_cursor()

    def update_cursor(self):
        from PyQt6.QtGui import QCursor, QPixmap
        import os
        from Src.Logic.paths import resource_path
        if self.is_zoomed:
            pm = QPixmap(resource_path(os.path.join("assets", "uisvg", "zoom_out.svg")))
            self.setCursor(QCursor(pm))
        else:
            pm = QPixmap(resource_path(os.path.join("assets", "uisvg", "zoom_in.svg")))
            self.setCursor(QCursor(pm))

    def set_raw_pixmap(self, pixmap):
        self._raw_pixmap = pixmap
        self.is_zoomed = False
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._scale_content()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.is_zoomed:
            self._scale_content()

    def _scale_content(self):
        if self.is_zoomed:
            return
        avail_w = self.width()
        avail_h = self.height()
        if avail_w <= 0 or avail_h <= 0:
            return
        if self._raw_pixmap and not self._raw_pixmap.isNull():
            scaled = self._raw_pixmap.scaled(
                avail_w, avail_h, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            super().setPixmap(scaled)

    def get_scroll_area(self):
        parent = self.parentWidget()
        while parent:
            if parent.__class__.__name__ == "QScrollArea":
                return parent
            parent = parent.parentWidget()
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_click_pos = event.position()
            from PyQt6.QtWidgets import QApplication
            self._single_click_timer.start(QApplication.doubleClickInterval())

    def _on_single_click(self):
        if self.is_zoomed or not self._last_click_pos:
            return
        
        x = self._last_click_pos.x()
        if x < self.width() / 2.0:
            self.clicked_left.emit()
        else:
            self.clicked_right.emit()

    def mouseDoubleClickEvent(self, event):
        self._single_click_timer.stop()
        
        if not self._raw_pixmap or self._raw_pixmap.isNull():
            return
            
        scroll_area = self.get_scroll_area()
        if not scroll_area:
            return

        if not self.is_zoomed:
            drawn_pixmap = self.pixmap()
            if not drawn_pixmap: return
            
            drawn_w = drawn_pixmap.width()
            drawn_h = drawn_pixmap.height()
            
            offset_x = (self.width() - drawn_w) / 2.0
            offset_y = (self.height() - drawn_h) / 2.0
            
            click_x = event.position().x()
            click_y = event.position().y()
            
            if click_x < offset_x or click_x > offset_x + drawn_w or click_y < offset_y or click_y > offset_y + drawn_h:
                return 
                
            prop_x = (click_x - offset_x) / drawn_w
            prop_y = (click_y - offset_y) / drawn_h
            
            self.is_zoomed = True
            
            raw_w = self._raw_pixmap.width()
            raw_h = self._raw_pixmap.height()
            
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.setMinimumSize(raw_w, raw_h)
            self.setMaximumSize(16777215, 16777215)
            super().setPixmap(self._raw_pixmap)
            
            def apply_scroll():
                from PyQt6.QtCore import QPoint
                content_widget = scroll_area.widget()
                if not content_widget:
                    return
                    
                new_offset_x = max(0, (self.width() - raw_w) / 2.0)
                new_offset_y = max(0, (self.height() - raw_h) / 2.0)
                
                target_x = int(new_offset_x + prop_x * raw_w)
                target_y = int(new_offset_y + prop_y * raw_h)
                
                target_pt = self.mapTo(content_widget, QPoint(target_x, target_y))
                
                viewport_w = scroll_area.viewport().width()
                viewport_h = scroll_area.viewport().height()
                
                scroll_area.horizontalScrollBar().setValue(int(target_pt.x() - viewport_w / 2.0))
                scroll_area.verticalScrollBar().setValue(int(target_pt.y() - viewport_h / 2.0))
            
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(50, apply_scroll)
            self.update_cursor()
        else:
            self.is_zoomed = False
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            self._scale_content()
            self.update_cursor()

    def wheelEvent(self, event):
        from PyQt6.QtCore import Qt
        scroll_area = self.get_scroll_area()
        if scroll_area and self.is_zoomed and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            h_bar = scroll_area.horizontalScrollBar()
            h_bar.setValue(h_bar.value() - event.angleDelta().y())
            event.accept()
        else:
            super().wheelEvent(event)

class MangaReaderWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.paths = []
        self.current_page = 0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Image Display
        self.image_label = ReaderImageLabel()
        self.image_label.setStyleSheet("background-color: #1e1e1e;")
        self.image_label.clicked_left.connect(self.prev_page)
        self.image_label.clicked_right.connect(self.next_page)
        self.layout.addWidget(self.image_label, stretch=1)

        # Toolbar
        self.toolbar_widget = QWidget()
        self.toolbar_widget.setStyleSheet("background-color: #2d2d2d; border-top: 1px solid #3d3d3d;")
        self.toolbar_layout = QHBoxLayout(self.toolbar_widget)
        self.toolbar_layout.setContentsMargins(10, 5, 10, 5)
        
        self.btn_prev = QPushButton("< Prev")
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev.clicked.connect(self.prev_page)
        
        self.page_input = QLineEdit()
        self.page_input.setFixedWidth(50)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.returnPressed.connect(self.jump_to_page)
        
        self.lbl_total = QLabel("/ 0")
        self.lbl_total.setStyleSheet("color: white;")
        
        self.btn_next = QPushButton("Next >")
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.clicked.connect(self.next_page)
        
        self.toolbar_layout.addStretch()
        self.toolbar_layout.addWidget(self.btn_prev)
        self.toolbar_layout.addWidget(self.page_input)
        self.toolbar_layout.addWidget(self.lbl_total)
        self.toolbar_layout.addWidget(self.btn_next)
        self.toolbar_layout.addStretch()
        
        self.layout.addWidget(self.toolbar_widget)

    def load_folder(self, folder, jump_to_path=None):
        exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
        files = [
            os.path.join(folder, f) for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in exts
        ]
        files.sort(key=lambda p: natural_key(os.path.basename(p)))
        
        self.paths = files
        self.current_page = 0
        if jump_to_path and jump_to_path in self.paths:
            self.current_page = self.paths.index(jump_to_path)
            
        self.lbl_total.setText(f"/ {len(self.paths)}")
        self.load_page()

    def load_page(self):
        if not self.paths or self.current_page < 0 or self.current_page >= len(self.paths):
            return
            
        path = self.paths[self.current_page]
        self.page_input.setText(str(self.current_page + 1))
        
        reader = QImageReader(path)
        image = reader.read()
        if not image.isNull():
            pixmap = QPixmap.fromImage(image)
            self.image_label.set_raw_pixmap(pixmap)
            
        self.setFocus()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.load_page()

    def next_page(self):
        if self.current_page < len(self.paths) - 1:
            self.current_page += 1
            self.load_page()
            
    def jump_to_page(self):
        try:
            page = int(self.page_input.text()) - 1
            if 0 <= page < len(self.paths):
                self.current_page = page
                self.load_page()
            else:
                self.page_input.setText(str(self.current_page + 1))
        except ValueError:
            self.page_input.setText(str(self.current_page + 1))
            
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            self.prev_page()
            event.accept()
        elif event.key() == Qt.Key.Key_Right:
            self.next_page()
            event.accept()
        else:
            super().keyPressEvent(event)