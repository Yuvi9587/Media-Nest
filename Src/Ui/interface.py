import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTreeView, 
                             QSplitter, QLabel, QPushButton, QScrollArea, QFrame, 
                             QSlider, QStyle, QLineEdit, QScrollBar, QSizePolicy, QProgressBar,
                             QListWidget, QListWidgetItem, QStackedWidget)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QPoint, QEvent
from PyQt6.QtGui import QMouseEvent, QPixmap, QIcon, QShortcut, QKeySequence, QCursor
from PyQt6.QtMultimediaWidgets import QVideoWidget

from Src.Ui.gallery import GallerySection
from Src.Ui.reader_widget import ManhwaReaderWidget, MangaReaderWidget
from Src.Logic.paths import resource_path
class JumpSlider(QSlider):
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            val = self.minimum() + ((self.maximum() - self.minimum()) * event.position().x()) / self.width()
            self.setValue(int(val))
            self.sliderMoved.emit(int(val))
            event.accept()
        super().mousePressEvent(event)

class CustomVideoWidget(QVideoWidget):
    skip_forward_signal = pyqtSignal()
    skip_backward_signal = pyqtSignal()
    toggle_play_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            self.skip_backward_signal.emit()

        elif event.key() == Qt.Key.Key_Right:
            self.skip_forward_signal.emit()

        elif event.key() == Qt.Key.Key_Space:
            self.toggle_play_signal.emit()

        else:
            super().keyPressEvent(event)



class DynamicImageLabel(QLabel):
    """A smart label that natively recalculates image/GIF scale during ANY UI resize (like dragging splitters)."""
    zoom_changed = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._raw_pixmap = None
        self.is_zoomed = False
        self._zoom_factor = 1.0
        
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

    def clear(self):
        self._raw_pixmap = None
        self.is_zoomed = False
        self._zoom_factor = 1.0
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        super().clear()
        self.update_cursor()

    def set_raw_pixmap(self, pixmap):
        self._raw_pixmap = pixmap
        self.is_zoomed = False
        self._zoom_factor = 1.0
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._scale_content()
        self.update_cursor()

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
            
        elif self.movie() and self.movie().isValid():
            orig_size = self.movie().currentImage().size()
            if not orig_size.isEmpty():
                ratio = min(avail_w / max(orig_size.width(), 1), avail_h / max(orig_size.height(), 1))
                new_w = int(orig_size.width() * ratio)
                new_h = int(orig_size.height() * ratio)
                self.movie().setScaledSize(QSize(new_w, new_h))

    def get_scroll_area(self):
        parent = self.parentWidget()
        while parent:
            if isinstance(parent, QScrollArea):
                return parent
            parent = parent.parentWidget()
        return None

    def mouseDoubleClickEvent(self, event):
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

class ZoomOverlay(QWidget):
    zoom_in_requested = pyqtSignal()
    zoom_out_requested = pyqtSignal()
    reset_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 5, 10, 5)
        self.layout.setSpacing(5)
        
        self.btn_minus = QPushButton("-")
        self.btn_minus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_minus.clicked.connect(self.zoom_out_requested.emit)
        
        self.lbl_percent = QLabel("100%")
        
        self.btn_plus = QPushButton("+")
        self.btn_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_plus.clicked.connect(self.zoom_in_requested.emit)
        
        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.clicked.connect(self.reset_requested.emit)
        
        self.layout.addWidget(self.btn_minus)
        self.layout.addWidget(self.lbl_percent)
        self.layout.addWidget(self.btn_plus)
        self.layout.addWidget(self.btn_reset)
        
        self.setStyleSheet("""
            ZoomOverlay {
                background-color: rgba(45, 45, 48, 220);
                border-radius: 8px;
                border: 1px solid #3e3e42;
            }
            QPushButton {
                background-color: #3e3e42;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #007acc;
            }
            QLabel {
                color: white;
                font-weight: bold;
                min-width: 45px;
                qproperty-alignment: AlignCenter;
            }
        """)
        
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)
        
        if parent:
            parent.installEventFilter(self)
            
    def eventFilter(self, obj, event):
        if obj == self.parent() and event.type() == QEvent.Type.Resize:
            self.update_position()
        return super().eventFilter(obj, event)
        
    def show_zoom(self, zoom_factor):
        if zoom_factor == 0.0:
            self.hide()
            return
            
        self.lbl_percent.setText(f"{int(zoom_factor * 100)}%")
        self.adjustSize()
        self.update_position()
        self.show()
        self.raise_()
        self.hide_timer.start(5000)
        
    def update_position(self):
        if self.parent():
            pr = self.parent().rect()
            self.move(pr.width() - self.width() - 30, 20)

class VideoContainer(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        self.video_widget = CustomVideoWidget(self)
        self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.video_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self.video_controls = QWidget(self)
        self.video_controls.setFixedHeight(95)
        self.video_controls.setStyleSheet("background-color: #111111;") 
        
        self.controls_layout = QVBoxLayout(self.video_controls)
        self.controls_layout.setContentsMargins(15, 10, 15, 10)
        self.controls_layout.setSpacing(5)
        
        self.timeline_layout = QHBoxLayout()
        
        self.lbl_current_time = QLabel("00:00")
        self.lbl_current_time.setStyleSheet("color: #cccccc; font-size: 1em; font-weight: bold;")
        
        self.slider_progress = JumpSlider(Qt.Orientation.Horizontal)
        self.slider_progress.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_progress.setStyleSheet("""
            QSlider::groove:horizontal { border-radius: 2px; height: 4px; background: #333333; }
            QSlider::handle:horizontal { background: #ff8c00; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
            QSlider::sub-page:horizontal { background: #ff8c00; border-radius: 2px; }
        """)
                
        self.lbl_total_time = QLabel("00:00")
        self.lbl_total_time.setStyleSheet("color: #cccccc; font-size: 1em; font-weight: bold;")
        
        self.timeline_layout.addWidget(self.lbl_current_time)
        self.timeline_layout.addWidget(self.slider_progress)
        self.timeline_layout.addWidget(self.lbl_total_time)
        
        self.buttons_layout = QHBoxLayout()
        
        self.asset_dir = main_window.ui.asset_dir
       
        def get_icon(name):
            return QIcon(os.path.join(self.asset_dir, "Svg", f"{name}.svg"))

        self.left_controls_container = QWidget()
        self.left_controls_container.setFixedWidth(250)
        self.left_controls_layout = QHBoxLayout(self.left_controls_container)
        self.left_controls_layout.setContentsMargins(0, 0, 0, 0)
        self.left_controls_layout.setSpacing(10)
        
        self.btn_volume = QPushButton()
        self.btn_volume.setIcon(get_icon("speaker-high"))
        self.btn_volume.setIconSize(QSize(24, 24))
        self.btn_volume.setFixedSize(40, 40)
        self.btn_volume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_volume.setStyleSheet("background: transparent; border: none; padding: 0px;")
        
        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(100)
        self.slider_volume.setFixedWidth(80)
        self.slider_volume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_volume.setStyleSheet("""
            QSlider::groove:horizontal { border-radius: 2px; height: 4px; background: #333333; }
            QSlider::handle:horizontal { background: #ff8c00; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }
            QSlider::sub-page:horizontal { background: #ff8c00; border-radius: 2px; }
        """)
        
        self.left_controls_layout.addWidget(self.btn_volume)
        self.left_controls_layout.addWidget(self.slider_volume)
        self.left_controls_layout.addStretch()
        
        self.center_controls_layout = QHBoxLayout()
        self.center_controls_layout.setSpacing(15) 
        
        icon_button_style = "QPushButton { background-color: transparent; border: none; padding: 0px; margin: 0px; }"
        
        self.btn_previous = QPushButton()
        self.btn_previous.setIcon(get_icon("previous"))
        self.btn_previous.setIconSize(QSize(24, 24))
        self.btn_previous.setFixedSize(40, 40)
        self.btn_previous.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_previous.setStyleSheet(icon_button_style)

        self.btn_skip_backward = QPushButton()
        self.btn_skip_backward.setIcon(get_icon("back 10Sec"))
        self.btn_skip_backward.setIconSize(QSize(28, 28))
        self.btn_skip_backward.setFixedSize(40, 40)
        self.btn_skip_backward.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_skip_backward.setStyleSheet(icon_button_style)
        
        self.btn_play = QPushButton()
        self.btn_play.setIcon(get_icon("play"))
        self.btn_play.setIconSize(QSize(36, 36)) 
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_play.setFixedSize(48, 48)
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play.setStyleSheet(icon_button_style)
        
        self.btn_skip_forward = QPushButton()
        self.btn_skip_forward.setIcon(get_icon("skip 10Sec"))
        self.btn_skip_forward.setIconSize(QSize(28, 28))
        self.btn_skip_forward.setFixedSize(40, 40)
        self.btn_skip_forward.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_skip_forward.setStyleSheet(icon_button_style)

        self.btn_next = QPushButton()
        self.btn_next.setIcon(get_icon("next"))
        self.btn_next.setIconSize(QSize(24, 24))
        self.btn_next.setFixedSize(40, 40)
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.setStyleSheet(icon_button_style)
        
        self.center_controls_layout.addWidget(self.btn_previous)
        self.center_controls_layout.addWidget(self.btn_skip_backward)
        self.center_controls_layout.addWidget(self.btn_play)
        self.center_controls_layout.addWidget(self.btn_skip_forward)
        self.center_controls_layout.addWidget(self.btn_next)
        
        self.right_controls_container = QWidget()
        self.right_controls_container.setFixedWidth(250)
        
        self.right_controls_layout = QHBoxLayout(self.right_controls_container)
        self.right_controls_layout.setContentsMargins(0, 0, 0, 0)
        self.right_controls_layout.addStretch() 
        
        self.btn_loop = QPushButton()
        self.btn_loop.setIcon(get_icon("repeat-off"))
        self.btn_loop.setIconSize(QSize(24, 24))
        self.btn_loop.setFixedSize(40, 40)
        self.btn_loop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_loop.setStyleSheet(icon_button_style)

        self.btn_fullscreen = QPushButton()
        self.btn_fullscreen.setIcon(get_icon("fullscreen"))
        self.btn_fullscreen.setIconSize(QSize(24, 24))
        self.btn_fullscreen.setFixedSize(40, 40)
        self.btn_fullscreen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fullscreen.setStyleSheet(icon_button_style)
        
        self.right_controls_layout.addWidget(self.btn_loop)
        self.right_controls_layout.addWidget(self.btn_fullscreen)        
        
        self.buttons_layout.addWidget(self.left_controls_container)
        self.buttons_layout.addStretch()
        self.buttons_layout.addLayout(self.center_controls_layout) 
        self.buttons_layout.addStretch()
        self.buttons_layout.addWidget(self.right_controls_container) 
        
        self.controls_layout.addLayout(self.timeline_layout)
        self.controls_layout.addLayout(self.buttons_layout)
        
        self.layout.addWidget(self.video_widget)
        self.layout.addWidget(self.video_controls)


class MainWindowUI:
    def setup_ui(self, main_window):
        main_window.resize(1200, 800)
        
        self.asset_dir = resource_path("assets")       
        self.central_widget = QWidget()
        main_window.setCentralWidget(self.central_widget)
        
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.horizontal_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_layout.addWidget(self.horizontal_splitter)

        self.setup_sidebar()
        self.setup_right_side(main_window)

        self.horizontal_splitter.addWidget(self.sidebar_widget)
        self.horizontal_splitter.addWidget(self.right_container)
        self.horizontal_splitter.setSizes([320, 880])

    def setup_sidebar(self):
        self.sidebar_widget = QWidget()
        self.sidebar_layout = QVBoxLayout(self.sidebar_widget)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)

        self.header_frame = QFrame()
        self.header_frame.setFixedHeight(80) 
        
        self.header_layout = QHBoxLayout(self.header_frame)
        self.header_layout.setContentsMargins(10, 5, 10, 5)
        self.header_layout.setSpacing(10)
        self.header_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.header_layout.addStretch()

        self.logo_container = QWidget()
        self.logo_container.setFixedHeight(80) 
        self.logo_container.setStyleSheet("background-color: transparent;") 
        
        logo_layout = QVBoxLayout(self.logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_sidebar_logo = QLabel()
        
        logo_path = resource_path(os.path.join("assets", "Logo.png"))
        logo_pixmap = QPixmap(logo_path)

        if not logo_pixmap.isNull():
            scaled_logo = logo_pixmap.scaled(
                260, 80, 
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.lbl_sidebar_logo.setPixmap(scaled_logo)
            self.lbl_sidebar_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            logo_layout.addWidget(self.lbl_sidebar_logo)
            self.header_layout.addWidget(self.logo_container)
            self.header_layout.addSpacing(15)

        self.btn_open = QPushButton("OPEN FOLDER")
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setFixedHeight(45)

        self.btn_open.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border-radius: 10px;
                font-weight: bold;
                font-size: 1.1em;
                padding: 0px 20px;
            }
            QPushButton:hover {
                background-color: #1890ff;
            }
        """)

        self.btn_load_db = QPushButton(" LOAD DB")
        self.btn_load_db.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_load_db.setFixedHeight(45) 

        self.btn_load_db.setStyleSheet("""
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

        self.btn_change_db = QPushButton()
        self.btn_change_db.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "settings.svg"))))
        self.btn_change_db.setIconSize(QSize(24, 24))
        self.btn_change_db.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_change_db.setFixedSize(45, 45) 
        self.btn_change_db.setToolTip("Change Database Folder")
        self.btn_change_db.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                color: white;
                border-radius: 10px;
                font-size: 1.5em;
                text-align: center;  
                padding: 0px;        
                padding-bottom: 2px;  
            }
            QPushButton:hover { background-color: #505050; }
        """)

        self.btn_detach = QPushButton() 
        self.btn_detach.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "detach.svg"))))
        self.btn_detach.setIconSize(QSize(20, 20))
        self.btn_detach.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_detach.setFixedSize(45, 45)
        self.btn_detach.setToolTip("Detach Viewer (Multi-Monitor)")
        self.btn_detach.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                color: white;
                border-radius: 10px;
                font-size: 1.5em;
            }
            QPushButton:hover { background-color: #505050; }
        """)

        self.btn_support = QPushButton()
        self.btn_support.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "heart.svg"))))
        self.btn_support.setIconSize(QSize(24, 24))
        self.btn_support.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_support.setFixedSize(45, 45)
        self.btn_support.setToolTip("Support & Community")
        self.btn_support.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                border-radius: 10px;
            }
            QPushButton:hover { background-color: #505050; }
        """)

        self.btn_terminal = QPushButton()
        self.btn_terminal.setIcon(QIcon(resource_path(os.path.join("assets", "uisvg", "terminal.svg"))))
        self.btn_terminal.setIconSize(QSize(24, 24))
        self.btn_terminal.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_terminal.setFixedSize(45, 45)
        self.btn_terminal.setToolTip("Power Terminal")
        self.btn_terminal.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                border-radius: 10px;
            }
            QPushButton:hover { background-color: #8957e5; }
        """)

        self.header_layout.addWidget(self.btn_open)
        self.header_layout.addWidget(self.btn_load_db)
        self.header_layout.addWidget(self.btn_change_db)
        self.header_layout.addWidget(self.btn_detach)
        self.header_layout.addWidget(self.btn_support)
        self.header_layout.addWidget(self.btn_terminal)
        self.header_layout.addStretch()

        self.sidebar_layout.addWidget(self.header_frame)

        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(10, 5, 10, 10)
        search_layout.setSpacing(8)

        
        asset_dir = resource_path("assets")

        self.search_icon_label = QLabel()
        search_pixmap = QPixmap(os.path.join(asset_dir, "Svg", "search.svg"))

        if not search_pixmap.isNull():
            search_pixmap = search_pixmap.scaled(
                18, 18,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.search_icon_label.setPixmap(search_pixmap)

        self.search_icon_label.setFixedWidth(24)
        self.search_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search files, folders, or .ext...")

        self.search_bar.setStyleSheet("""
            QLineEdit {
                background-color: #252526;
                color: white;
                border: 1px solid #3e3e42;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 1em;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
                background-color: #2d2d30;
            }
        """)

        search_layout.addWidget(self.search_icon_label)
        search_layout.addWidget(self.search_bar)

        self.sidebar_layout.addWidget(search_container)

        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setFixedHeight(4)
        self.loading_bar.setStyleSheet("QProgressBar { border: none; background-color: transparent; } QProgressBar::chunk { background-color: #007acc; border-radius: 2px; }")
        self.loading_bar.hide()
        self.sidebar_layout.addWidget(self.loading_bar)

        self.sidebar_vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.sidebar_vertical_splitter.setChildrenCollapsible(False)

        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(20)

        self.sidebar_vertical_splitter.addWidget(self.tree_view)

        self.tag_viewer_container = QWidget()
        self.tag_viewer_layout = QVBoxLayout(self.tag_viewer_container)
        self.tag_viewer_layout.setContentsMargins(10, 5, 10, 10)
        self.tag_viewer_layout.setSpacing(5)
        
        self.tag_viewer_header_container = QWidget()
        self.tag_viewer_header_layout = QHBoxLayout(self.tag_viewer_header_container)
        self.tag_viewer_header_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tag_viewer_header = QLabel("Tags")
        self.tag_viewer_header.setStyleSheet("color: #cccccc; font-weight: bold; font-size: 1em;")
        
        self.tag_search_input = QLineEdit()
        self.tag_search_input.setPlaceholderText("Search...")
        self.tag_search_input.setMaximumWidth(120)
        self.tag_search_input.setStyleSheet("QLineEdit { background-color: #252526; color: #d4d4d4; border: 1px solid #3e3e42; border-radius: 4px; padding: 2px 4px; }")
        
        self.btn_toggle_tags = QPushButton()
        self.btn_toggle_tags.setIcon(QIcon(resource_path("assets/uisvg/hide_tags.svg")))
        self.btn_toggle_tags.setIconSize(QSize(20, 20))
        self.btn_toggle_tags.setFixedSize(28, 28)
        self.btn_toggle_tags.setStyleSheet("""
            QPushButton { 
                border: none; 
                background: transparent; 
                padding: 4px; 
            } 
            QPushButton:hover { 
                background-color: #333333; 
                border-radius: 4px; 
            }
        """)
        self.btn_toggle_tags.clicked.connect(self.toggle_tag_list)
        self.tag_search_input.textChanged.connect(self.filter_tag_list)
        
        self.tag_viewer_header_layout.addWidget(self.tag_viewer_header)
        self.tag_viewer_header_layout.addStretch()
        self.tag_viewer_header_layout.addWidget(self.tag_search_input)
        self.tag_viewer_header_layout.addSpacing(5)
        self.tag_viewer_header_layout.addWidget(self.btn_toggle_tags)
        
        self.tag_viewer_header_layout.addSpacing(5)
        
        self.tag_list_widget = QListWidget()
        self.tag_list_widget.setStyleSheet("""
            QListWidget {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 4px;
            }
            QListWidget::item {
                background-color: #333333;
                border-radius: 4px;
                margin: 2px;
                padding: 4px;
            }
            QListWidget::item:hover {
                background-color: #444444;
            }
            QListWidget::item:selected {
                background-color: #007acc;
                color: white;
            }
        """)
        self.tag_list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.tag_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tag_list_widget.setWrapping(True)
        self.tag_list_widget.setFlow(QListWidget.Flow.LeftToRight)
        self.tag_list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.tag_list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.tag_edit_container = QWidget()
        self.tag_edit_layout = QHBoxLayout(self.tag_edit_container)
        self.tag_edit_layout.setContentsMargins(0, 0, 0, 0)
        self.tag_edit_layout.setSpacing(5)

        self.input_new_tag = QLineEdit()
        self.input_new_tag.setPlaceholderText("Add tag...")
        self.input_new_tag.setFixedHeight(30)
        self.input_new_tag.setStyleSheet("QLineEdit { background-color: #252526; color: #d4d4d4; border: 1px solid #3e3e42; border-radius: 4px; padding: 4px; }")

        self.btn_add_tag_main = QPushButton()
        self.btn_add_tag_main.setIcon(QIcon(resource_path("assets/uisvg/add.svg")))
        self.btn_add_tag_main.setIconSize(QSize(16, 16))
        self.btn_add_tag_main.setFixedSize(40, 30)
        self.btn_add_tag_main.setStyleSheet("QPushButton { background-color: #3e3e42; border: none; border-radius: 4px; padding: 7px 12px; } QPushButton:hover { background-color: #505050; }")
        self.btn_add_tag_main.setToolTip("Add Tag")

        self.btn_delete_tag_main = QPushButton()
        self.btn_delete_tag_main.setIcon(QIcon(resource_path("assets/uisvg/remove.svg")))
        self.btn_delete_tag_main.setIconSize(QSize(16, 16))
        self.btn_delete_tag_main.setFixedSize(40, 30)
        self.btn_delete_tag_main.setStyleSheet("QPushButton { background-color: #3e3e42; border: none; border-radius: 4px; padding: 7px 12px; } QPushButton:hover { background-color: #505050; }")
        self.btn_delete_tag_main.setToolTip("Delete Selected Tag")

        self.tag_edit_layout.addWidget(self.input_new_tag)
        self.tag_edit_layout.addWidget(self.btn_add_tag_main)
        self.tag_edit_layout.addWidget(self.btn_delete_tag_main)

        self.tag_viewer_layout.addWidget(self.tag_viewer_header_container)
        self.tag_viewer_layout.addWidget(self.tag_list_widget)
        self.tag_viewer_layout.addWidget(self.tag_edit_container)
        
        self.tag_viewer_container.hide()

        self.bottom_stack = QStackedWidget()
        self.bottom_stack.addWidget(self.tag_viewer_container)   
        self.file_info_panel = self._build_file_info_panel()     
        self.bottom_stack.addWidget(self.file_info_panel)
        self.bottom_stack.setCurrentIndex(0)
        self.bottom_stack.hide()   

        self.sidebar_vertical_splitter.addWidget(self.bottom_stack)
        self.sidebar_layout.addWidget(self.sidebar_vertical_splitter)
        self.sidebar_vertical_splitter.setSizes([600, 200])

    def filter_tag_list(self, text):
        search_term = text.lower()
        for i in range(self.tag_list_widget.count()):
            item = self.tag_list_widget.item(i)
            item.setHidden(search_term not in item.text().lower())

    def show_tags_in_stack(self):
        """Switch the bottom stack back to the Tags page and make it visible."""
        self.bottom_stack.setCurrentIndex(0)
        self.bottom_stack.setMaximumHeight(16777215)
        if self.bottom_stack.isHidden():
            self.bottom_stack.show()
            sizes = self.sidebar_vertical_splitter.sizes()
            total = sum(sizes)
            self.sidebar_vertical_splitter.setSizes([max(total - 200, 100), 200])

    def show_file_info_in_stack(self):
        """Switch the bottom stack to the File Info page and make it visible."""
        self.bottom_stack.setCurrentIndex(1)
        self.bottom_stack.setMaximumHeight(16777215)
        if self.bottom_stack.isHidden():
            self.bottom_stack.show()
            sizes = self.sidebar_vertical_splitter.sizes()
            total = sum(sizes)
            self.sidebar_vertical_splitter.setSizes([max(total - 220, 100), 220])

    def toggle_tag_list(self):
        is_hidden = self.tag_list_widget.isHidden()
        if is_hidden:
            self.bottom_stack.setMaximumHeight(16777215)
            self.tag_list_widget.show()
            if hasattr(self, 'tag_edit_container'): self.tag_edit_container.show()
            if hasattr(self, 'tag_search_input'): self.tag_search_input.show()
            self.btn_toggle_tags.setIcon(QIcon(resource_path("assets/uisvg/hide_tags.svg")))
            if hasattr(self, 'sidebar_vertical_splitter'):
                sizes = self.sidebar_vertical_splitter.sizes()
                total = sum(sizes)
                self.sidebar_vertical_splitter.setSizes([max(total - 200, 0), 200])
        else:
            self.tag_list_widget.hide()
            if hasattr(self, 'tag_edit_container'): self.tag_edit_container.hide()
            if hasattr(self, 'tag_search_input'): self.tag_search_input.hide()
            self.btn_toggle_tags.setIcon(QIcon(resource_path("assets/uisvg/unhide_tags.svg")))
            if hasattr(self, 'sidebar_vertical_splitter'):
                self.bottom_stack.setMaximumHeight(43)
                sizes = self.sidebar_vertical_splitter.sizes()
                total = sum(sizes)
                self.sidebar_vertical_splitter.setSizes([total, 43])

    def setup_right_side(self, main_window):
        self.right_container = QWidget()
        self.right_layout = QVBoxLayout(self.right_container)
        self.right_layout.setContentsMargins(0, 0, 0, 0)

        self.vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.viewer_widget = QWidget()
        self.viewer_layout = QVBoxLayout(self.viewer_widget)
        self.viewer_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_placeholder = QLabel("Select media")
        self.lbl_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_placeholder.setStyleSheet("color: #6e6e6e; font-size: 1.2em;")
        
        self.image_view_container = QWidget()
        self.image_view_layout = QHBoxLayout(self.image_view_container)
        self.image_view_layout.setContentsMargins(0, 0, 0, 0)
        self.image_view_layout.setSpacing(2)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.viewer_stack_widget = QWidget()
        self.viewer_stack_layout = QVBoxLayout(self.viewer_stack_widget)
        self.viewer_stack_layout.setContentsMargins(0,0,0,0)

        self.lbl_image = DynamicImageLabel()
        self.viewer_stack_layout.addWidget(self.lbl_image)

        self.manhwa_reader = ManhwaReaderWidget(self.scroll_area)
        self.viewer_stack_layout.addWidget(self.manhwa_reader)
        self.manhwa_reader.hide()
        
        self.manga_reader = MangaReaderWidget()
        self.viewer_stack_layout.addWidget(self.manga_reader)
        self.manga_reader.hide()

        self.scroll_area.setWidget(self.viewer_stack_widget)

        self.scroll_area.verticalScrollBar().valueChanged.connect(self.manhwa_reader.scroll_update)

        self.manhwa_zoom_slider = QSlider(Qt.Orientation.Vertical)
        self.manhwa_zoom_slider.setRange(50, 200) 
        self.manhwa_zoom_slider.setValue(100)     
        self.manhwa_zoom_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.manhwa_zoom_slider.setStyleSheet("""
            QSlider::groove:vertical { border-radius: 2px; width: 6px; background: #333333; }
            QSlider::handle:vertical { background: #0e639c; height: 16px; width: 16px; margin: 0 -5px; border-radius: 8px; }
            QSlider::sub-page:vertical { background: #333333; border-radius: 2px; }
            QSlider::add-page:vertical { background: #0e639c; border-radius: 2px; }
        """)
        self.manhwa_zoom_slider.hide()

        self.main_scrollbar = QScrollBar(Qt.Orientation.Vertical)
        self.main_scrollbar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.main_scrollbar.setStyleSheet("""
            QScrollBar:vertical { background: #1e1e1e; width: 14px; margin: 0px; border-left: 1px solid #333333; }
            QScrollBar::handle:vertical { background: #424242; min-height: 20px; border-radius: 6px; margin: 2px; }
            QScrollBar::handle:vertical:hover { background: #4f4f4f; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        """)

        real_sb = self.scroll_area.verticalScrollBar()
        real_sb.rangeChanged.connect(self.main_scrollbar.setRange)
        real_sb.valueChanged.connect(self.main_scrollbar.setValue)
        self.main_scrollbar.valueChanged.connect(real_sb.setValue)
        
        def sync_scroll_state(min_val, max_val):
            self.main_scrollbar.setPageStep(real_sb.pageStep())
            self.main_scrollbar.setSingleStep(real_sb.singleStep())
            if max_val <= 0:
                self.main_scrollbar.hide()
            else:
                self.main_scrollbar.show()
                
        real_sb.rangeChanged.connect(sync_scroll_state)

        self.image_view_layout.addWidget(self.scroll_area)
        self.image_view_layout.addWidget(self.manhwa_zoom_slider)
        self.image_view_layout.addWidget(self.main_scrollbar)

        self.zoom_overlay = ZoomOverlay(self.image_view_container)
        self.zoom_overlay.hide()
        
        self.lbl_image.zoom_changed.connect(self.zoom_overlay.show_zoom)
        self.zoom_overlay.zoom_in_requested.connect(self.lbl_image.zoom_in_keyboard)
        self.zoom_overlay.zoom_out_requested.connect(self.lbl_image.zoom_out_keyboard)
        self.zoom_overlay.reset_requested.connect(self.lbl_image.reset_zoom)
        
        self.manga_reader.image_label.zoom_changed.connect(self.zoom_overlay.show_zoom)
        self.zoom_overlay.zoom_in_requested.connect(self.manga_reader.image_label.zoom_in_keyboard)
        self.zoom_overlay.zoom_out_requested.connect(self.manga_reader.image_label.zoom_out_keyboard)
        self.zoom_overlay.reset_requested.connect(self.manga_reader.image_label.reset_zoom)

        self.image_view_container.hide() 

        self.video_container = VideoContainer(main_window)
        
        self.video_widget = self.video_container.video_widget
        self.video_controls = self.video_container.video_controls
        self.btn_play = self.video_container.btn_play
        self.btn_skip_backward = self.video_container.btn_skip_backward
        self.btn_skip_forward = self.video_container.btn_skip_forward
        self.btn_previous = self.video_container.btn_previous   
        self.btn_next = self.video_container.btn_next                 
        self.btn_fullscreen = self.video_container.btn_fullscreen       
        self.btn_loop = self.video_container.btn_loop               
        self.btn_volume = self.video_container.btn_volume           
        self.slider_volume = self.video_container.slider_volume     
        self.slider_progress = self.video_container.slider_progress
        self.lbl_current_time = self.video_container.lbl_current_time
        self.lbl_total_time = self.video_container.lbl_total_time

        self.video_container.hide()

        self.viewer_layout.addWidget(self.lbl_placeholder)
        self.viewer_layout.addWidget(self.image_view_container)
        self.viewer_layout.addWidget(self.video_container)

        self.gallery_section = GallerySection()
        self.vertical_splitter.addWidget(self.viewer_widget)
        self.vertical_splitter.addWidget(self.gallery_section)
        self.vertical_splitter.setSizes([600, 200])
        self.right_layout.addWidget(self.vertical_splitter)

    def svg_path(self, name):
        return os.path.join(self.asset_dir, "Svg", f"{name}.svg")

    def _build_file_info_panel(self):
        """Creates the file info panel that replaces the Tags section in the splitter."""
        panel = QWidget()
        panel.setObjectName("FileInfoPanel")

        outer_layout = QVBoxLayout(panel)
        outer_layout.setContentsMargins(10, 8, 10, 10)
        outer_layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)

        icon_lbl = QLabel("ℹ")
        icon_lbl.setStyleSheet("color: #569cd6; font-size: 1.15em; font-weight: bold;")
        icon_lbl.setFixedWidth(18)

        title_lbl = QLabel("File Info")
        title_lbl.setStyleSheet(
            "color: #cccccc; font-size: 0.9em; font-weight: bold; letter-spacing: 0.5px;"
        )

        btn_close = QPushButton("✕")
        btn_close.setObjectName("FileInfoCloseBtn")
        btn_close.setFixedSize(22, 22)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setToolTip("Close File Info – return to Tags")
        btn_close.setStyleSheet("""
            QPushButton#FileInfoCloseBtn {
                background-color: transparent;
                color: #888888;
                border: none;
                font-size: 0.9em;
                font-weight: bold;
                border-radius: 11px;
            }
            QPushButton#FileInfoCloseBtn:hover {
                background-color: #c0392b;
                color: white;
            }
        """)
        panel.btn_close = btn_close

        header_row.addWidget(icon_lbl)
        header_row.addWidget(title_lbl)
        header_row.addStretch()
        header_row.addWidget(btn_close)
        outer_layout.addLayout(header_row)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(
            "background-color: #3e3e42; max-height: 1px; border: none; margin: 2px 0px;"
        )
        outer_layout.addWidget(divider)

        row_style_key   = "color: #7a7a9a; font-size: 0.85em;"
        row_style_value = "color: #d4d4d4; font-size: 0.85em;"

        def make_row(key):
            row = QHBoxLayout()
            row.setContentsMargins(0, 2, 0, 2)
            row.setSpacing(8)
            k = QLabel(key)
            k.setStyleSheet(row_style_key)
            k.setFixedWidth(64)
            k.setAlignment(Qt.AlignmentFlag.AlignTop)
            v = QLabel("—")
            v.setStyleSheet(row_style_value)
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(k)
            row.addWidget(v, 1)
            return row, v

        row_name,       panel.lbl_info_name       = make_row("Name:")
        row_type,       panel.lbl_info_type       = make_row("Type:")
        row_size,       panel.lbl_info_size       = make_row("Size:")
        row_resolution, panel.lbl_info_resolution = make_row("Resolution:")
        row_duration,   panel.lbl_info_duration   = make_row("Duration:")
        row_modified,   panel.lbl_info_modified   = make_row("Modified:")
        row_path,       panel.lbl_info_path       = make_row("Path:")

        for row in (row_name, row_type, row_size, row_resolution, row_duration,
                    row_modified, row_path):
            outer_layout.addLayout(row)

        outer_layout.addStretch()
        return panel
