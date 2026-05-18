# Src/Ui/reader_widget.py
import os
import bisect
import re
from collections import OrderedDict

from PyQt6.QtCore import Qt, QRect, QSize, QRunnable, QThreadPool, pyqtSignal, QObject
from PyQt6.QtGui import QPainter, QPixmap, QColor, QImageReader
from PyQt6.QtWidgets import QWidget

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
        
        # --- NEW ZOOM VARIABLES ---
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