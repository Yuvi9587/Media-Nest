import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTreeView, 
                             QSplitter, QLabel, QPushButton, QScrollArea, QFrame, 
                             QSlider, QStyle, QLineEdit, QScrollBar, QSizePolicy)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QMouseEvent, QPixmap, QIcon
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import pyqtSignal

# Import our custom Gallery
from Src.Ui.gallery import GallerySection
from Src.Ui.reader_widget import ManhwaReaderWidget, MangaReaderWidget
from Src.Logic.paths import resource_path
# --- CUSTOM SLIDER ---
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
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 🔹 This is the magic line that lets it shrink and expand freely when splitters are dragged
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._raw_pixmap = None
        self.is_zoomed = False
        self.update_cursor()

    def update_cursor(self):
        from PyQt6.QtGui import QCursor, QPixmap
        import os
        if self.is_zoomed:
            pm = QPixmap(os.path.join("assets", "uisvg", "zoom_out.svg"))
            self.setCursor(QCursor(pm))
        else:
            pm = QPixmap(os.path.join("assets", "uisvg", "zoom_in.svg"))
            self.setCursor(QCursor(pm))

    def clear(self):
        self._raw_pixmap = None
        self.is_zoomed = False
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        super().clear()
        self.update_cursor()

    def set_raw_pixmap(self, pixmap):
        self._raw_pixmap = pixmap
        self.is_zoomed = False
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

        # 1. Handle Static Images
        if self._raw_pixmap and not self._raw_pixmap.isNull():
            scaled = self._raw_pixmap.scaled(
                avail_w, avail_h, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            super().setPixmap(scaled) 
            
        # 2. Handle Animated GIFs
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
            # We are zooming IN.
            drawn_pixmap = self.pixmap()
            if not drawn_pixmap: return
            
            drawn_w = drawn_pixmap.width()
            drawn_h = drawn_pixmap.height()
            
            # Find top-left of the drawn image
            offset_x = (self.width() - drawn_w) / 2.0
            offset_y = (self.height() - drawn_h) / 2.0
            
            click_x = event.position().x()
            click_y = event.position().y()
            
            # Prevent zooming if clicked on the black borders
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
            # We are zooming OUT.
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
            # angleDelta().y() is positive for scrolling up. Going up = scrolling left (decreasing value).
            h_bar.setValue(h_bar.value() - event.angleDelta().y())
            event.accept()
        else:
            super().wheelEvent(event)

class VideoContainer(QWidget):
    def __init__(self, main_window):
        super().__init__()
        # Use a vertical layout with ZERO spacing so the video and controls touch perfectly
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Top: The video player
        self.video_widget = CustomVideoWidget(self)
        self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.video_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Bottom: The Windows Media Player style control bar
        self.video_controls = QWidget(self)
        self.video_controls.setFixedHeight(95)
        self.video_controls.setStyleSheet("background-color: #111111;") 
        
        self.controls_layout = QVBoxLayout(self.video_controls)
        self.controls_layout.setContentsMargins(15, 10, 15, 10)
        self.controls_layout.setSpacing(5)
        
        # --- ROW 1: THE TIMELINE ---
        self.timeline_layout = QHBoxLayout()
        
        self.lbl_current_time = QLabel("00:00")
        self.lbl_current_time.setStyleSheet("color: #cccccc; font-size: 13px; font-weight: bold;")
        
        self.slider_progress = JumpSlider(Qt.Orientation.Horizontal)
        self.slider_progress.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_progress.setStyleSheet("""
            QSlider::groove:horizontal { border-radius: 2px; height: 4px; background: #333333; }
            QSlider::handle:horizontal { background: #ff8c00; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
            QSlider::sub-page:horizontal { background: #ff8c00; border-radius: 2px; }
        """)
                
        self.lbl_total_time = QLabel("00:00")
        self.lbl_total_time.setStyleSheet("color: #cccccc; font-size: 13px; font-weight: bold;")
        
        self.timeline_layout.addWidget(self.lbl_current_time)
        self.timeline_layout.addWidget(self.slider_progress)
        self.timeline_layout.addWidget(self.lbl_total_time)
        
        # --- ROW 2: BUTTONS ---
        self.buttons_layout = QHBoxLayout()
        
        # Helper function to easily load icons from your assets folder
        self.asset_dir = main_window.ui.asset_dir
       
        def get_icon(name):
            return QIcon(os.path.join(self.asset_dir, "Svg", f"{name}.svg"))

        # --- Left Side Controls (Volume) ---
        self.left_controls_layout = QHBoxLayout()
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
        
        # --- Center Controls (Previous, Skip Back, Play, Skip Forward, Next) ---
        self.center_controls_layout = QHBoxLayout()
        self.center_controls_layout.setSpacing(15) 
        
        # Shared style for the transparent SVG buttons
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
        
        # Add them in the correct order!
        self.center_controls_layout.addWidget(self.btn_previous)
        self.center_controls_layout.addWidget(self.btn_skip_backward)
        self.center_controls_layout.addWidget(self.btn_play)
        self.center_controls_layout.addWidget(self.btn_skip_forward)
        self.center_controls_layout.addWidget(self.btn_next)
        
        # --- Right Side Controls (Loop & Fullscreen) ---
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
        
        # Assemble Row 2
        self.buttons_layout.addLayout(self.left_controls_layout)
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
        self.horizontal_splitter.setSizes([280, 920])

    def setup_sidebar(self):
        self.sidebar_widget = QWidget()
        self.sidebar_layout = QVBoxLayout(self.sidebar_widget)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)

        # ================= HEADER =================
        self.header_frame = QFrame()
        self.header_frame.setFixedHeight(80) 
        
        self.header_layout = QHBoxLayout(self.header_frame)
        self.header_layout.setContentsMargins(10, 5, 10, 5)
        self.header_layout.setSpacing(10)
        self.header_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.header_layout.addStretch()

        # --- Logo ---
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

        # --- Open Folder Button ---
        self.btn_open = QPushButton("OPEN FOLDER")
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setFixedHeight(45)

        self.btn_open.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border-radius: 10px;
                font-weight: bold;
                font-size: 14px;
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
                font-size: 14px;     
                padding: 0px 20px;   
            }
            QPushButton:hover { background-color: #2ea043; }
        """)

        # --- Change DB Folder Button ---
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
                font-size: 20px;
                text-align: center;  
                padding: 0px;        
                padding-bottom: 2px;  
            }
            QPushButton:hover { background-color: #505050; }
        """)

        # --- Detach Viewer Button ---
        self.btn_detach = QPushButton("⧉") 
        self.btn_detach.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_detach.setFixedSize(45, 45)
        self.btn_detach.setToolTip("Detach Viewer (Multi-Monitor)")
        self.btn_detach.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                color: white;
                border-radius: 10px;
                font-size: 20px;
            }
            QPushButton:hover { background-color: #505050; }
        """)

        self.header_layout.addWidget(self.btn_open)
        self.header_layout.addWidget(self.btn_load_db)
        self.header_layout.addWidget(self.btn_change_db)
        self.header_layout.addWidget(self.btn_detach)
        self.header_layout.addStretch()

        self.sidebar_layout.addWidget(self.header_frame)

        # ================= SEARCH BAR =================
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(10, 5, 10, 10)
        search_layout.setSpacing(8)

        
        asset_dir = resource_path("assets")

        # --- Search Icon ---
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

        # --- Search LineEdit ---
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search files, folders, or .ext...")

        self.search_bar.setStyleSheet("""
            QLineEdit {
                background-color: #252526;
                color: white;
                border: 1px solid #3e3e42;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
                background-color: #2d2d30;
            }
        """)

        search_layout.addWidget(self.search_icon_label)
        search_layout.addWidget(self.search_bar)

        self.sidebar_layout.addWidget(search_container)

        # ================= TREE VIEW =================
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(20)

        self.sidebar_layout.addWidget(self.tree_view)

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
        self.lbl_placeholder.setStyleSheet("color: #6e6e6e; font-size: 16px;")
        
        # ==========================================
        # 🔹 MANHWA VIEWER LAYOUT
        # ==========================================
        self.image_view_container = QWidget()
        self.image_view_layout = QHBoxLayout(self.image_view_container)
        self.image_view_layout.setContentsMargins(0, 0, 0, 0)
        self.image_view_layout.setSpacing(2)

        # 1. The Scroll Area (Image Viewer)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # We use a container widget so we can swap between the Standard viewer and the Manhwa viewer
        self.viewer_stack_widget = QWidget()
        self.viewer_stack_layout = QVBoxLayout(self.viewer_stack_widget)
        self.viewer_stack_layout.setContentsMargins(0,0,0,0)

        # Standard Viewer (For GIFs and single images)
        self.lbl_image = DynamicImageLabel() # 👈 Use our new smart label!
        self.viewer_stack_layout.addWidget(self.lbl_image)

        # High-Performance Virtual Reader (For folders)
        self.manhwa_reader = ManhwaReaderWidget(self.scroll_area)
        self.viewer_stack_layout.addWidget(self.manhwa_reader)
        self.manhwa_reader.hide() # Hidden by default
        
        # Classic Manga Reader
        self.manga_reader = MangaReaderWidget()
        self.viewer_stack_layout.addWidget(self.manga_reader)
        self.manga_reader.hide() # Hidden by default

        self.scroll_area.setWidget(self.viewer_stack_widget)

        # Connect the scrollbar to the virtual reader so it knows when to load images!
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.manhwa_reader.scroll_update)

        # 2. The Zoom Slider (Hidden until Manhwa loaded)
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

        # 3. The Custom External Scrollbar
        self.main_scrollbar = QScrollBar(Qt.Orientation.Vertical)
        self.main_scrollbar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.main_scrollbar.setStyleSheet("""
            QScrollBar:vertical { background: #1e1e1e; width: 14px; margin: 0px; border-left: 1px solid #333333; }
            QScrollBar::handle:vertical { background: #424242; min-height: 20px; border-radius: 6px; margin: 2px; }
            QScrollBar::handle:vertical:hover { background: #4f4f4f; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        """)

        # Sync the hidden native scrollbar with our custom one
        real_sb = self.scroll_area.verticalScrollBar()
        real_sb.rangeChanged.connect(self.main_scrollbar.setRange)
        real_sb.valueChanged.connect(self.main_scrollbar.setValue)
        self.main_scrollbar.valueChanged.connect(real_sb.setValue)
        
        # Hide the custom scrollbar when it's not needed (just like native behavior)
        def sync_scroll_state(min_val, max_val):
            self.main_scrollbar.setPageStep(real_sb.pageStep())
            self.main_scrollbar.setSingleStep(real_sb.singleStep())
            if max_val <= 0:
                self.main_scrollbar.hide()
            else:
                self.main_scrollbar.show()
                
        real_sb.rangeChanged.connect(sync_scroll_state)

        # 🔹 ADD WIDGETS IN THE EXACT ORDER REQUESTED:
        self.image_view_layout.addWidget(self.scroll_area)        # Left: Image
        self.image_view_layout.addWidget(self.manhwa_zoom_slider) # Middle: Zoom Slider
        self.image_view_layout.addWidget(self.main_scrollbar)     # Right: Custom Scrollbar

        self.image_view_container.hide() 

        # ==========================================
        # VIDEO CONTAINER SETUP
        # ==========================================
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