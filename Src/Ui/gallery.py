from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QPushButton,
    QAbstractItemView
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap


class GallerySection(QWidget):
    file_selected = pyqtSignal(str)

    # --- SIZE MODES ---
    SMALL = (140, 170, 120)
    MEDIUM = (190, 220, 170)
    LARGE = (240, 260, 220)

    def __init__(self):
        super().__init__()

        # Default mode = Large (your current one)
        self.current_mode = "large"
        self.TILE_WIDTH, self.TILE_HEIGHT, self.ICON_SIZE = self.LARGE

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # ===============================
        # HEADER (Title + Size Button)
        # ===============================
        header_container = QWidget()
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(10, 5, 10, 5)

        self.lbl_header = QLabel("Gallery Grid")
        self.lbl_header.setStyleSheet("""
            color: #cccccc;
            font-weight: bold;
        """)

        self.btn_size_toggle = QPushButton("Large")
        self.btn_size_toggle.setFixedHeight(28)
        self.btn_size_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_size_toggle.setStyleSheet("""
            QPushButton {
                background-color: #333;
                color: white;
                border-radius: 6px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #444;
            }
        """)

        header_layout.addWidget(self.lbl_header)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_size_toggle)

        header_container.setStyleSheet("""
            background-color: #252526;
            border-bottom: 1px solid #333;
        """)

        self.layout.addWidget(header_container)

        # ===============================
        # LIST WIDGET (Grid)
        # ===============================
        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)

        self.list_widget.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        self.list_widget.setGridSize(QSize(self.TILE_WIDTH, self.TILE_HEIGHT))

        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setSpacing(0)
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

    # ===============================
    # SIZE TOGGLE LOGIC
    # ===============================
    def toggle_size_mode(self):

        if self.current_mode == "large":
            self.current_mode = "medium"
            width, height, icon = self.MEDIUM
            self.btn_size_toggle.setText("Medium")

        elif self.current_mode == "medium":
            self.current_mode = "small"
            width, height, icon = self.SMALL
            self.btn_size_toggle.setText("Small")

        else:
            self.current_mode = "large"
            width, height, icon = self.LARGE
            self.btn_size_toggle.setText("Large")

        self.TILE_WIDTH = width
        self.TILE_HEIGHT = height
        self.ICON_SIZE = icon

        self.list_widget.setIconSize(QSize(icon, icon))
        self.list_widget.setGridSize(QSize(width, height))

        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setSizeHint(QSize(width, height))

    # ===============================
    # POPULATE GRID
    # ===============================
    def populate(self, items):
        self.list_widget.clear()

        for name, path, is_video in items:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, path)

            item.setSizeHint(QSize(self.TILE_WIDTH, self.TILE_HEIGHT))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            item.setToolTip(name)

            if is_video:
                item.setText(f"🎬 {name}")
            else:
                item.setText(f"🖼️ {name}")

            self.list_widget.addItem(item)

    # ===============================
    # CLICK EVENT
    # ===============================
    def on_item_clicked(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        self.file_selected.emit(path)