import os
import bisect
import re
from collections import OrderedDict

from PyQt6.QtCore import Qt, QRect, QSize, QRunnable, QThreadPool, pyqtSignal, QObject, QTimer, QPoint
from PyQt6.QtGui import QPainter, QPixmap, QColor, QImageReader, QCursor, QShortcut, QKeySequence
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel, QSizePolicy, QApplication
from PyQt6.QtSvg import QSvgRenderer
from Src.Logic.paths import resource_path

def natural_key(text):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", text)]

class LoaderSignals(QObject):
    loaded = pyqtSignal(str, QPixmap, QSize)

class ImageLoader(QRunnable):
    def __init__(self, path, target_width, signals):
        super().__init__()
        self.path = path
        self.target_width = target_width 
        self.signals = signals

    def run(self):
        reader = QImageReader(self.path)
        image = reader.read()
        
        if image.isNull():
            return

        pixmap = QPixmap.fromImage(image)
        
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
        
        self.zoom_factor = 1.0
        self.viewport_width = 1000
        self.current_target_width = 1000
        self.setMinimumWidth(self.viewport_width)

        # Autoscroll state
        self._autoscroll_active = False
        self._autoscroll_global_origin = None
        self._autoscroll_viewport_origin = None
        self._autoscroll_timer = QTimer(self)
        self._autoscroll_timer.timeout.connect(self._do_autoscroll)
        self.setMouseTracking(True)
        
        try:
            self.autoscroll_renderer = QSvgRenderer(resource_path(os.path.join("assets", "uisvg", "autoscroll.svg")))
        except Exception:
            self.autoscroll_renderer = None

    def set_zoom(self, percentage):
        self.zoom_factor = percentage / 100.0
        
        visible_width = self.scroll_area.viewport().width()
        self.current_target_width = int(visible_width * self.zoom_factor)
        
        self.setMinimumWidth(max(visible_width, self.current_target_width))
        
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
        
        self.load_pages(files, jump_to_path)

    def load_pages(self, paths, jump_to_path=None):
        self.paths = paths
        self.page_heights = [self.estimated_height for _ in self.paths]
        self.recalculate_offsets()
        self.cache.clear()
        self.loading.clear()
        
        self.update()
        self.load_visible_images()

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
            
        orig_w = size.width()
        orig_h = size.height()
        
        if orig_w > 0:
            ratio = self.current_target_width / orig_w
            scaled_height = int(orig_h * ratio)
        else:
            scaled_height = orig_h
            
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
            worker = ImageLoader(path, self.current_target_width, self.signals)
            self.thread_pool.start(worker)

    def scroll_update(self):
        self.load_visible_images()
        self.update()

    def _do_autoscroll(self):
        if not self._autoscroll_active: return
        
        current_global = QCursor.pos()
        dy = current_global.y() - self._autoscroll_global_origin.y()
        
        if abs(dy) < 15: return
        
        speed = (abs(dy) - 15) * 0.15
        if speed > 60: speed = 60
        if dy < 0: speed = -speed
        
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(int(scrollbar.value() + speed))
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            if not self._autoscroll_active:
                self._autoscroll_active = True
                self._autoscroll_global_origin = event.globalPosition().toPoint()
                self._autoscroll_viewport_origin = self.scroll_area.viewport().mapFromGlobal(self._autoscroll_global_origin)
                self._autoscroll_timer.start(16)
                
                # Replace cursor with the SVG
                if self.autoscroll_renderer:
                    pm = QPixmap(32, 32)
                    pm.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(pm)
                    self.autoscroll_renderer.render(painter)
                    painter.end()
                    self.setCursor(QCursor(pm, 16, 16))
            else:
                self._autoscroll_active = False
                self._autoscroll_timer.stop()
                self.unsetCursor()
            self.update()
            event.accept()
        elif self._autoscroll_active:
            self._autoscroll_active = False
            self._autoscroll_timer.stop()
            self.unsetCursor()
            self.update()
            super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        
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
    zoom_changed = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.is_zoomed = False
        self._zoom_factor = 1.0
        self._raw_pixmap = None
        self._single_click_timer = QTimer()
        self._single_click_timer.setSingleShot(True)
        self._single_click_timer.timeout.connect(self._on_single_click)
        self._last_click_pos = None
        
        self.shortcut_zoom_in_1 = QShortcut(QKeySequence("Ctrl++"), self)
        self.shortcut_zoom_in_1.activated.connect(self.zoom_in_keyboard)
        self.shortcut_zoom_in_2 = QShortcut(QKeySequence("Ctrl+="), self)
        self.shortcut_zoom_in_2.activated.connect(self.zoom_in_keyboard)
        
        self.shortcut_zoom_out = QShortcut(QKeySequence("Ctrl+-"), self)
        self.shortcut_zoom_out.activated.connect(self.zoom_out_keyboard)
        
        self.update_cursor()

    def update_cursor(self):
        if self.is_zoomed:
            pm = QPixmap(resource_path(os.path.join("assets", "uisvg", "zoom_out.svg")))
            self.setCursor(QCursor(pm))
        else:
            pm = QPixmap(resource_path(os.path.join("assets", "uisvg", "zoom_in.svg")))
            self.setCursor(QCursor(pm))

    def set_raw_pixmap(self, pixmap):
        self._raw_pixmap = pixmap
        self.is_zoomed = False
        self._zoom_factor = 1.0
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
            self._zoom_factor = 1.0
            self.zoom_changed.emit(self._zoom_factor)
            
            raw_w = self._raw_pixmap.width()
            raw_h = self._raw_pixmap.height()
            
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.setMinimumSize(raw_w, raw_h)
            self.setMaximumSize(16777215, 16777215)
            super().setPixmap(self._raw_pixmap)
            
            def apply_scroll():
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
            
            QTimer.singleShot(50, apply_scroll)
            self.update_cursor()
        else:
            self.reset_zoom()

    def reset_zoom(self):
        if self.is_zoomed:
            self.is_zoomed = False
            self._zoom_factor = 1.0
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            self._scale_content()
            self.update_cursor()
            self.zoom_changed.emit(0.0)

    def zoom_in_keyboard(self):
        if self.is_zoomed:
            self._apply_zoom(1.1)

    def zoom_out_keyboard(self):
        if self.is_zoomed:
            self._apply_zoom(1 / 1.1)

    def _apply_zoom(self, factor, focus_pos=None):
        scroll_area = self.get_scroll_area()
        if not scroll_area or not self._raw_pixmap or self._raw_pixmap.isNull():
            return
            
        if self.width() == 0 or self.height() == 0:
            return

        drawn_pixmap = self.pixmap()
        if not drawn_pixmap:
            return

        drawn_w = drawn_pixmap.width()
        drawn_h = drawn_pixmap.height()
        
        offset_x = (self.width() - drawn_w) / 2.0
        offset_y = (self.height() - drawn_h) / 2.0
        
        if focus_pos:
            mouse_x = focus_pos.x()
            mouse_y = focus_pos.y()
            viewport_pos = self.mapTo(scroll_area.viewport(), focus_pos)
        else:
            viewport_center = scroll_area.viewport().rect().center()
            label_center = self.mapFrom(scroll_area.viewport(), viewport_center)
            mouse_x = label_center.x()
            mouse_y = label_center.y()
            viewport_pos = viewport_center

        if mouse_x < offset_x: mouse_x = offset_x
        if mouse_x > offset_x + drawn_w: mouse_x = offset_x + drawn_w
        if mouse_y < offset_y: mouse_y = offset_y
        if mouse_y > offset_y + drawn_h: mouse_y = offset_y + drawn_h
        
        prop_x = (mouse_x - offset_x) / drawn_w
        prop_y = (mouse_y - offset_y) / drawn_h

        new_zoom = self._zoom_factor * factor
        
        if new_zoom < 0.1: new_zoom = 0.1
        if new_zoom > 10.0: new_zoom = 10.0
        
        self._zoom_factor = new_zoom
        self.zoom_changed.emit(self._zoom_factor)
        
        raw_w = self._raw_pixmap.width()
        raw_h = self._raw_pixmap.height()
        
        new_w = max(1, int(raw_w * self._zoom_factor))
        new_h = max(1, int(raw_h * self._zoom_factor))
        
        self.setMinimumSize(new_w, new_h)
        
        scaled_pixmap = self._raw_pixmap.scaled(
            new_w, new_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
        )
        super().setPixmap(scaled_pixmap)
        
        def apply_scroll():
            content_widget = scroll_area.widget()
            if not content_widget:
                return
            
            new_offset_x = max(0, (self.width() - new_w) / 2.0)
            new_offset_y = max(0, (self.height() - new_h) / 2.0)
            
            target_x = int(new_offset_x + prop_x * new_w)
            target_y = int(new_offset_y + prop_y * new_h)
            
            target_pt = self.mapTo(content_widget, QPoint(target_x, target_y))
            
            new_scroll_x = target_pt.x() - viewport_pos.x()
            new_scroll_y = target_pt.y() - viewport_pos.y()
            
            scroll_area.horizontalScrollBar().setValue(new_scroll_x)
            scroll_area.verticalScrollBar().setValue(new_scroll_y)
            
        QTimer.singleShot(0, apply_scroll)

    def wheelEvent(self, event):
        scroll_area = self.get_scroll_area()
        if scroll_area and self.is_zoomed and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                return
            factor = 1.1 if delta > 0 else (1 / 1.1)
            self._apply_zoom(factor, event.position().toPoint())
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
        
        self.image_label = ReaderImageLabel()
        self.image_label.setStyleSheet("background-color: #1e1e1e;")
        self.image_label.clicked_left.connect(self.prev_page)
        self.image_label.clicked_right.connect(self.next_page)
        self.layout.addWidget(self.image_label, stretch=1)

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
        
        self.load_pages(files, jump_to_path)

    def load_pages(self, paths, jump_to_path=None):
        if paths and isinstance(paths[0], str):
            self.paths = [(p, False) for p in paths]
        else:
            self.paths = paths
            
        self.spreads = []
        i = 0
        while i < len(self.paths):
            p, is_attached = self.paths[i]
            if is_attached and i + 1 < len(self.paths):
                self.spreads.append((p, self.paths[i+1][0]))
                i += 2
            else:
                self.spreads.append((p,))
                i += 1
                
        self.current_page = 0
        if jump_to_path:
            for idx, spread in enumerate(self.spreads):
                if jump_to_path in spread:
                    self.current_page = idx
                    break
                    
        self.lbl_total.setText(f"/ {len(self.spreads)}")
        self.load_page()

    def load_page(self):
        if not hasattr(self, 'spreads') or not self.spreads or self.current_page < 0 or self.current_page >= len(self.spreads):
            return
            
        spread = self.spreads[self.current_page]
        self.page_input.setText(str(self.current_page + 1))
        
        reader = QImageReader(spread[0])
        image = reader.read()
        
        if len(spread) == 2:
            next_reader = QImageReader(spread[1])
            next_image = next_reader.read()
            
            if not image.isNull() and not next_image.isNull():
                target_h = max(image.height(), next_image.height())
                
                if image.height() != target_h:
                    image = image.scaledToHeight(target_h, Qt.TransformationMode.SmoothTransformation)
                if next_image.height() != target_h:
                    next_image = next_image.scaledToHeight(target_h, Qt.TransformationMode.SmoothTransformation)
                    
                combined = QPixmap(image.width() + next_image.width(), target_h)
                combined.fill(Qt.GlobalColor.black)
                
                painter = QPainter(combined)
                painter.drawImage(0, 0, image)
                painter.drawImage(image.width(), 0, next_image)
                painter.end()
                
                self.image_label.set_raw_pixmap(combined)
            elif not image.isNull():
                self.image_label.set_raw_pixmap(QPixmap.fromImage(image))
        else:
            if not image.isNull():
                self.image_label.set_raw_pixmap(QPixmap.fromImage(image))
            
        self.setFocus()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.load_page()

    def next_page(self):
        if self.current_page < len(self.spreads) - 1:
            self.current_page += 1
            self.load_page()
            
    def jump_to_page(self):
        try:
            page = int(self.page_input.text()) - 1
            if 0 <= page < len(self.spreads):
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