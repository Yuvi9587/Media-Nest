import os
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QPushButton,
    QAbstractItemView,
    QComboBox,
    QLineEdit
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon


class GallerySection(QWidget):
    file_selected = pyqtSignal(str)

    SMALL = (140, 170, 120)
    MEDIUM = (190, 220, 170)
    LARGE = (240, 260, 220)

    def __init__(self):
        super().__init__()

        self.current_mode = "large"
        self.TILE_WIDTH, self.TILE_HEIGHT, self.ICON_SIZE = self.LARGE

        from Src.Logic.paths import resource_path
        self.asset_dir = resource_path("assets")
        self.svg_dir = os.path.join(self.asset_dir, "Svg")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        header_container = QWidget()
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(10, 5, 10, 5)

        self.lbl_header = QLabel("Gallery Grid")
        self.lbl_header.setStyleSheet("""
            color: #cccccc;
            font-weight: bold;
        """)

        self.name_filter_input = QLineEdit()
        self.name_filter_input.setPlaceholderText("Filter by name...")
        self.name_filter_input.setFixedWidth(180)
        self.name_filter_input.setStyleSheet("""
            QLineEdit {
                background-color: #2d2d30;
                color: white;
                border: 1px solid #3e3e42;
                border-radius: 6px;
                padding: 4px 10px;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
        """)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Images", "Videos"])
        self.filter_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.filter_combo.setStyleSheet("""
            QComboBox { 
                background-color: #2d2d30; 
                color: white; 
                border: 1px solid #3e3e42; 
                border-radius: 6px; 
                padding: 4px 10px; 
                font-weight: bold;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #252526;
                color: white;
                selection-background-color: #007acc;
            }
        """)

        self.btn_size_toggle = QPushButton()
        self.btn_size_toggle.setFixedSize(42, 32)
        self.btn_size_toggle.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_size_toggle.setStyleSheet("""
            QPushButton {
                background-color: #2d2d30;
                border-radius: 6px;
                border: 1px solid #3e3e42;
                padding: 0px;
                text-align: center;
            }
            QPushButton:hover {
                background-color: #3a3a3d;
            }
        """)

        self.btn_size_toggle.setIcon(QIcon(os.path.join(self.svg_dir, "large.svg")))
        self.btn_size_toggle.setIconSize(QSize(20, 20))
        self.btn_size_toggle.setContentsMargins(0, 0, 0, 0)

        header_layout.addWidget(self.lbl_header)
        header_layout.addStretch()
        header_layout.addWidget(self.name_filter_input) 
        header_layout.addWidget(self.filter_combo)
        header_layout.addWidget(self.btn_size_toggle)

        header_container.setStyleSheet("""
            background-color: #252526;
            border-bottom: 1px solid #333;
        """)

        self.layout.addWidget(header_container)

        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        self.list_widget.setGridSize(QSize(self.TILE_WIDTH, self.TILE_HEIGHT))
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setSpacing(0)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setWordWrap(False)
        self.list_widget.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: #101010;
                border: none;
                outline: none;
            }
            QListWidget::item {
                color: #eeeeee;
                border-radius: 4px;
                padding: 5px;
                border: 1px solid transparent;
            }
            QListWidget::item:hover:!selected {
                background-color: #1f1f1f;
                border: 1px solid #3e3e42;
            }
            QListWidget::item:selected {
                background-color: #004578;
                color: white;
                border: 1px solid #005a9e;
            }
        """)

        self.list_widget.itemClicked.connect(self.on_item_clicked)
        self.btn_size_toggle.clicked.connect(self.toggle_size_mode)

        self.layout.addWidget(self.list_widget)

    def toggle_size_mode(self):
        if self.current_mode == "large":
            self.current_mode = "medium"
            width, height, icon = self.MEDIUM
            self.btn_size_toggle.setIcon(
                QIcon(os.path.join(self.svg_dir, "medium.svg"))
            )

        elif self.current_mode == "medium":
            self.current_mode = "small"
            width, height, icon = self.SMALL
            self.btn_size_toggle.setIcon(
                QIcon(os.path.join(self.svg_dir, "small.svg"))
            )

        else:
            self.current_mode = "large"
            width, height, icon = self.LARGE
            self.btn_size_toggle.setIcon(
                QIcon(os.path.join(self.svg_dir, "large.svg"))
            )

        self.TILE_WIDTH = width
        self.TILE_HEIGHT = height
        self.ICON_SIZE = icon

        self.list_widget.setIconSize(QSize(icon, icon))
        self.list_widget.setGridSize(QSize(width, height))

        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setSizeHint(QSize(width, height))

    def populate(self, items):
        self.list_widget.clear()

        for name, path, is_video in items:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setSizeHint(QSize(self.TILE_WIDTH, self.TILE_HEIGHT))
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
            )
            item.setToolTip(name)

            from PyQt6.QtGui import QIcon
            import os
            svg_path = os.path.join(self.asset_dir, "uisvg")

            if is_video:
                item.setIcon(QIcon(os.path.join(svg_path, "video.svg")))
                item.setText(name)
            else:
                item.setIcon(QIcon(os.path.join(svg_path, "image.svg")))
                item.setText(name)

            self.list_widget.addItem(item)

    def on_item_clicked(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        self.file_selected.emit(path)

    def set_size_mode(self, target_mode):
        """Forces the gallery into small, medium, or large mode."""
        self.current_mode = target_mode
        
        if target_mode == "small":
            width, height, icon = self.SMALL
            icon_name = "small.svg"
        elif target_mode == "medium":
            width, height, icon = self.MEDIUM
            icon_name = "medium.svg"
        else:
            width, height, icon = self.LARGE
            icon_name = "large.svg"

        if hasattr(self, 'btn_size_toggle'):
            self.btn_size_toggle.setIcon(QIcon(os.path.join(self.svg_dir, icon_name)))

        self.TILE_WIDTH = width
        self.TILE_HEIGHT = height
        self.ICON_SIZE = icon

        self.list_widget.setIconSize(QSize(icon, icon))
        self.list_widget.setGridSize(QSize(width, height))

        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setSizeHint(QSize(width, height))