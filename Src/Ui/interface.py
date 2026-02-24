import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTreeView, 
                             QSplitter, QLabel, QPushButton, QScrollArea, QFrame, 
                             QSlider, QStyle, QLineEdit) # <-- ADD QLineEdit HERE
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtMultimediaWidgets import QVideoWidget

# Import our custom Gallery
from Src.Ui.gallery import GallerySection

# --- CUSTOM SLIDER ---
class JumpSlider(QSlider):
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            val = self.minimum() + ((self.maximum() - self.minimum()) * event.position().x()) / self.width()
            self.setValue(int(val))
            self.sliderMoved.emit(int(val))
            event.accept()
        super().mousePressEvent(event)

# --- WINDOWS 11 STYLE VIDEO CONTAINER ---
class VideoContainer(QWidget):
    def __init__(self, main_window):
        super().__init__()
        # Use a vertical layout with ZERO spacing so the video and controls touch perfectly
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Top: The video player
        self.video_widget = QVideoWidget(self)
        
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
        
        # --- ROW 2: BUTTONS & TITLE ---
        self.buttons_layout = QHBoxLayout()
        
        self.lbl_title = QLabel("Video Title")
        self.lbl_title.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        self.lbl_title.setFixedWidth(250) 
        
        # --- Center Controls (Skip Back, Play, Skip Forward) ---
        self.center_controls_layout = QHBoxLayout()
        self.center_controls_layout.setSpacing(15) 
        
        self.btn_skip_backward = QPushButton("⏪")
        self.btn_skip_backward.setFixedSize(40, 40)
        self.btn_skip_backward.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.btn_play = QPushButton("▶️")
        self.btn_play.setFixedSize(48, 48)
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.btn_skip_forward = QPushButton("⏩")
        self.btn_skip_forward.setFixedSize(40, 40)
        self.btn_skip_forward.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Shared styling for all central buttons
        button_style = """
            QPushButton { 
                background-color: transparent; 
                border: none; 
                color: white; 
                font-size: %s; 
                text-align: center;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover { color: #ff8c00; }
        """
        
        self.btn_skip_backward.setStyleSheet(button_style % "22px")
        self.btn_play.setStyleSheet(button_style % "28px") # Slightly larger to be the focal point
        self.btn_skip_forward.setStyleSheet(button_style % "22px")
        
        self.center_controls_layout.addWidget(self.btn_skip_backward)
        self.center_controls_layout.addWidget(self.btn_play)
        self.center_controls_layout.addWidget(self.btn_skip_forward)
        
        # --- Right Side Controls (Fullscreen) ---
        self.right_controls_container = QWidget()
        self.right_controls_container.setFixedWidth(250) # Set width on the WIDGET to balance the title
        
        self.right_controls_layout = QHBoxLayout(self.right_controls_container)
        self.right_controls_layout.setContentsMargins(0, 0, 0, 0)
        self.right_controls_layout.addStretch() # Push button to the right edge
        
        self.btn_fullscreen = QPushButton("⛶")
        self.btn_fullscreen.setFixedSize(40, 40)
        self.btn_fullscreen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fullscreen.setStyleSheet(button_style % "20px")
        
        self.right_controls_layout.addWidget(self.btn_fullscreen)
        
        # Assemble Row 2
        self.buttons_layout.addWidget(self.lbl_title, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.buttons_layout.addStretch()
        self.buttons_layout.addLayout(self.center_controls_layout) 
        self.buttons_layout.addStretch()
        self.buttons_layout.addWidget(self.right_controls_container) # Added the container widget here
        
        self.controls_layout.addLayout(self.timeline_layout)
        self.controls_layout.addLayout(self.buttons_layout)
        
        self.layout.addWidget(self.video_widget)
        self.layout.addWidget(self.video_controls)

class MainWindowUI:
    def setup_ui(self, main_window):
        main_window.resize(1200, 800)
        self.central_widget = QWidget()
        main_window.setCentralWidget(self.central_widget)
        
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_layout.addWidget(self.main_splitter)

        self.setup_sidebar()
        self.setup_right_side(main_window)

        self.main_splitter.addWidget(self.sidebar_widget)
        self.main_splitter.addWidget(self.right_container)
        self.main_splitter.setSizes([250, 950])

    def setup_sidebar(self):
        self.sidebar_widget = QWidget()
        self.sidebar_layout = QVBoxLayout(self.sidebar_widget)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        
        self.header_frame = QFrame()
        self.header_frame.setFixedHeight(70) 
        self.header_layout = QHBoxLayout(self.header_frame)
        self.header_layout.setContentsMargins(10, 5, 10, 5) 
        self.header_layout.setSpacing(10) 
        
        # --- INVISIBLE SPRING ON THE LEFT ---
        self.header_layout.addStretch()
        
        # 1. Add the Logo
        self.lbl_sidebar_logo = QLabel()
        logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "Logo.png"))
        logo_pixmap = QPixmap(logo_path)
        
        if not logo_pixmap.isNull():
            scaled_logo = logo_pixmap.scaled(
                240, 70,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.lbl_sidebar_logo.setPixmap(scaled_logo)
            self.lbl_sidebar_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_sidebar_logo.setStyleSheet("""
                QLabel {
                    background-color: transparent;
                    padding: 5px 0px;
                }
            """)         
            self.header_layout.addWidget(self.lbl_sidebar_logo)
            self.header_layout.addSpacing(15)

        # 2. Add the Open Folder button
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
        
        self.header_layout.addWidget(self.btn_open)
        
        # --- INVISIBLE SPRING ON THE RIGHT ---
        self.header_layout.addStretch()

        self.sidebar_layout.addWidget(self.header_frame)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Search files, folders, or .ext...")
        self.search_bar.setStyleSheet("""
            QLineEdit {
                background-color: #252526;
                color: white;
                border: 1px solid #3e3e42;
                border-radius: 6px;
                padding: 8px 12px;
                margin: 5px 10px 10px 10px; /* Spacing below the header */
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #007acc; /* Turns blue when clicked */
                background-color: #2d2d30;
            }
        """)
        self.sidebar_layout.addWidget(self.search_bar)

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
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.lbl_image)
        self.scroll_area.hide()

        self.video_container = VideoContainer(main_window)
        
        self.video_widget = self.video_container.video_widget
        self.video_controls = self.video_container.video_controls
        self.btn_play = self.video_container.btn_play
        self.btn_skip_backward = self.video_container.btn_skip_backward
        self.btn_skip_forward = self.video_container.btn_skip_forward
        self.btn_fullscreen = self.video_container.btn_fullscreen       
        self.slider_progress = self.video_container.slider_progress
        self.lbl_current_time = self.video_container.lbl_current_time
        self.lbl_total_time = self.video_container.lbl_total_time
        self.lbl_title = self.video_container.lbl_title

        self.video_container.hide()

        self.viewer_layout.addWidget(self.lbl_placeholder)
        self.viewer_layout.addWidget(self.scroll_area)
        self.viewer_layout.addWidget(self.video_container)

        self.gallery_section = GallerySection()
        self.vertical_splitter.addWidget(self.viewer_widget)
        self.vertical_splitter.addWidget(self.gallery_section)
        self.vertical_splitter.setSizes([600, 200])
        self.right_layout.addWidget(self.vertical_splitter)