import os
import sys
import json
import sqlite3
import shutil
import copy
import uuid
import traceback

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QGroupBox, QFileDialog, 
                             QMessageBox, QTabWidget, QWidget, QComboBox, 
                             QScrollArea, QProgressBar, QCheckBox, QSlider, 
                             QFrame, QApplication, QSizePolicy, QInputDialog, 
                             QGridLayout, QCompleter, QPlainTextEdit, QSplitter,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QAbstractItemView, QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSettings, QStringListModel, QUrl
from PyQt6.QtGui import QPixmap, QImageReader, QImage, QIcon, QPainter, QShortcut, QKeySequence
from PyQt6.QtMultimedia import QMediaPlayer

from send2trash import send2trash  
from Src.Logic.deduplication import DeduplicationWorker
from Src.Logic.video_dedup import VideoDedupTab
from Src.Logic.tags import TagManagerTab
from Src.Dialogs.setup_dialog import FirstTimeSetupDialog
from Src.Logic.pagination_tab import PaginationTab
from Src.Logic.db_repair import DbRepairTab
class ThumbnailWorker(QThread):
    thumb_ready = pyqtSignal(str, QImage, str, str) 

    def __init__(self, file_paths):
        super().__init__()
        self.file_paths = file_paths

    def run(self):
        for path in self.file_paths:
            if not os.path.exists(path): continue
            
            reader = QImageReader(path)
            orig_size = reader.size()
            res_text = f"{orig_size.width()}x{orig_size.height()}" if orig_size.isValid() else "Unknown"
            size_mb = f"{os.path.getsize(path) / (1024 * 1024):.2f}"
            
            if orig_size.isValid():
                reader.setScaledSize(orig_size.scaled(90, 90, Qt.AspectRatioMode.KeepAspectRatio))
                img = reader.read()
                if not img.isNull():
                    self.thumb_ready.emit(path, img, res_text, size_mb)

class FocusableClickableLabel(QLabel):
    clicked = pyqtSignal(str) 
    focused = pyqtSignal(str, QWidget)
    
    def __init__(self, file_path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_path = file_path
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.file_path)
            self.setFocus()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.setStyleSheet("background-color: #1e1e1e; border: 2px solid #0e639c; border-radius: 6px;")
        self.focused.emit(self.file_path, self)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.setStyleSheet("background-color: #1e1e1e; border: 1px solid #454545; border-radius: 6px;")

class ResizableImageLabel(QLabel):
    """A QLabel that automatically scales its pixmap to fit its maximum available space."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMinimumSize(10, 10)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._original_pixmap = None
        self._scaled_pixmap = None
        self._last_size = None
        
    def setPixmap(self, pixmap):
        self._original_pixmap = pixmap
        self._scaled_pixmap = None
        super().setPixmap(pixmap) # Set a base pixmap to give it a size hint if needed, though we override paint
        self.update()

    def resizeEvent(self, event):
        self._scaled_pixmap = None
        super().resizeEvent(event)

    def paintEvent(self, event):
        if not self._original_pixmap or self._original_pixmap.isNull():
            super().paintEvent(event)
            return

        if self._scaled_pixmap is None or self._last_size != self.size():
            self._scaled_pixmap = self._original_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self._last_size = self.size()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        x = (self.width() - self._scaled_pixmap.width()) // 2
        y = (self.height() - self._scaled_pixmap.height()) // 2
        painter.drawPixmap(x, y, self._scaled_pixmap)

class SettingsDialog(QDialog):
    def __init__(self, config_path, parent=None):
        super().__init__(parent)
        self.main_app = parent
        self.setWindowTitle("Media Nest Settings")
        self.setMinimumWidth(1100) 
        self.setMinimumHeight(700)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
            self.asset_base_dir = getattr(sys, '_MEIPASS', os.path.abspath("."))
        else:
            base_dir = os.path.abspath(".") 
            self.asset_base_dir = base_dir
            
        self.config_path = os.path.join(base_dir, "config.json")
        self.current_db_folder = ""
        self.current_ui_scale = "1.0" 
        
        self.db_folder_changed = False
        self.ui_scale_changed = False
        self.dedupe_worker = None
        self.lbl_preview_placeholder = None
        self.active_preview_group = -1
        self.current_preview_path = ""
        self.thumb_worker = None
        self.current_duplicate_groups = []
        
        self.undo_stack = []
        self.undo_trash_dir = "" 
        self.auto_delete_mode = "safe" 
        self.skip_group_auto_delete_confirm = False
        
        self.thumb_labels_map = {} 
        self.nav_groups = []

        self.scale_map = {
            "50%": "0.5", "70%": "0.7", "90%": "0.9", "100% (Default)": "1.0",
            "125%": "1.25", "150%": "1.5", "175%": "1.75", "200%": "2.0"
        }
        self.reverse_scale_map = {v: k for k, v in self.scale_map.items()}
        self.current_perf_mode = "balanced"
        self.perf_map = {
            "High Performance (Max Speed)": "high",
            "Balanced (Default)": "balanced",
            "Power Saver / Low End PC": "low"
        }
        self.reverse_perf_map = {v: k for k, v in self.perf_map.items()}

        self.load_config()
        self.setup_ui()
    def load_config(self):
        
        self.current_strictness = 0 
        
        settings = QSettings("MediaNest", "AppConfig")
        self.current_db_folder = settings.value("db_folder_path", "", type=str)

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    config = json.load(f)
                    
                    if not self.current_db_folder:
                        self.current_db_folder = config.get("db_folder", "")
                        
                    self.current_ui_scale = config.get("ui_scale", "1.0")
                    try:
                        if float(self.current_ui_scale) < 0.4:
                            self.current_ui_scale = "0.4"
                    except (ValueError, TypeError):
                        pass
                    self.current_strictness = config.get("dedupe_strictness", 0) 
                    self.current_perf_mode = config.get("performance_mode", "balanced")
            except Exception:
                pass

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tab_database = QWidget()
        self.tab_interface = QWidget()
        self.tab_dedupe = QWidget() 
        
        self.tab_tag_manager = None
        self.tab_tag_placeholder = QWidget()
        
        self.tab_video_dedup = None
        self.tab_video_placeholder = QWidget()
        
        self.tab_pagination = None
        self.tab_pagination_placeholder = QWidget()
        
        self.tabs.addTab(self.tab_database, "Database")
        self.tabs.addTab(self.tab_interface, "Interface")
        self.tabs.addTab(self.tab_tag_placeholder, "Tag Manager") 
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.tabs.addTab(self.tab_dedupe, "Image Dedup")
        self.tabs.addTab(self.tab_video_placeholder, "Video Dedup")
        self.tabs.addTab(self.tab_pagination_placeholder, "Pagination")

        db_layout = QVBoxLayout(self.tab_database)
        db_layout.setContentsMargins(8, 8, 8, 8)
        db_layout.setSpacing(6)

        db_group = QGroupBox("Database Setup")
        db_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        db_inner_layout = QVBoxLayout()
        db_inner_layout.setContentsMargins(8, 6, 8, 6)
        db_row = QHBoxLayout()
        db_row.addWidget(QLabel("Library Folder:"))
        self.db_path_input = QLineEdit(self.current_db_folder)
        db_row.addWidget(self.db_path_input)
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.clicked.connect(self.browse_folder)
        db_row.addWidget(self.btn_browse)
        db_inner_layout.addLayout(db_row)
        db_group.setLayout(db_inner_layout)
        db_layout.addWidget(db_group)

        self.db_repair_tab = DbRepairTab(self)
        db_layout.addWidget(self.db_repair_tab, stretch=1)



        ui_layout = QVBoxLayout(self.tab_interface)
        ui_group = QGroupBox("Visual & Performance Settings")
        ui_inner_layout = QVBoxLayout()
        ui_inner_layout.setSpacing(15)
        
        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("Window UI Scale (Requires Restart):"))
        self.combo_scale = QComboBox()
        
        current_text = self.reverse_scale_map.get(self.current_ui_scale)
        if not current_text:
            try:
                val = int(float(self.current_ui_scale) * 100)
                current_text = f"{val}%"
                self.scale_map[current_text] = self.current_ui_scale
            except (ValueError, TypeError):
                current_text = "100% (Default)"
                
        self.combo_scale.addItems(list(self.scale_map.keys()))
        self.combo_scale.addItem("Custom...")
        self.combo_scale.setCurrentText(current_text)
        
        self._last_scale_text = current_text
        self.combo_scale.currentTextChanged.connect(self.on_scale_changed)
        
        scale_row.addWidget(self.combo_scale)
        scale_row.addStretch() 
        ui_inner_layout.addLayout(scale_row)
        
        perf_row = QHBoxLayout()
        perf_row.addWidget(QLabel("Performance Mode:"))
        self.combo_perf = QComboBox()
        self.combo_perf.addItems(list(self.perf_map.keys()))
        self.combo_perf.setCurrentText(self.reverse_perf_map.get(self.current_perf_mode, "Balanced (Default)"))
        self.combo_perf.setToolTip("Adjusts how aggressively background thumbnails and AI workers consume CPU.")
        perf_row.addWidget(self.combo_perf)
        perf_row.addStretch()
        ui_inner_layout.addLayout(perf_row)
        
        ui_group.setLayout(ui_inner_layout)
        ui_layout.addWidget(ui_group)
        ui_layout.addStretch()

        dedupe_layout = QVBoxLayout(self.tab_dedupe)
        dedupe_layout.setContentsMargins(10, 15, 10, 10)
        dedupe_layout.setSpacing(15)

        command_panel = QFrame()
        command_panel.setObjectName("CommandPanel")
        command_layout = QVBoxLayout(command_panel)
        command_layout.setContentsMargins(15, 15, 15, 15)
        
        target_tag_row = QHBoxLayout()
        self.dedupe_target_tag_input = QLineEdit()
        self.dedupe_target_tag_input.setFixedHeight(36)
        self.dedupe_target_tag_input.setPlaceholderText("Target specific tag to scan (e.g. creator:example_name)...")
        
        target_tag_row.addWidget(self.dedupe_target_tag_input)
        command_layout.addLayout(target_tag_row)


        action_row = QHBoxLayout()
        self.btn_scan_dupes = QPushButton("Scan Library")
        self.btn_scan_dupes.setFixedSize(140, 36)
        self.btn_scan_dupes.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan_dupes.clicked.connect(lambda: self.start_dedupe_scan(is_auto_rescan=False)) 
        
        self.btn_auto_delete = QPushButton("Auto-Delete Low Res")
        self.btn_auto_delete.setFixedSize(210, 36)
        self.btn_auto_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto_delete.setEnabled(False)
        self.btn_auto_delete.clicked.connect(self.auto_delete_low_res)

        self.dedupe_search_bar = QLineEdit()
        self.dedupe_search_bar.setFixedHeight(36)
        self.dedupe_search_bar.setPlaceholderText("Filter duplicates by tags...")
        self.dedupe_search_bar.setEnabled(False)
        self.dedupe_search_bar.textChanged.connect(self.filter_duplicates)

        action_row.addWidget(self.btn_scan_dupes)
        action_row.addWidget(self.btn_auto_delete)
        action_row.addWidget(self.dedupe_search_bar)
        command_layout.addLayout(action_row)

        status_row = QHBoxLayout()
        self.lbl_strictness = QLabel("Strictness: Exact Matches Only (0 diffs)")
        self.lbl_strictness.setFixedWidth(240)
        self.lbl_strictness.setStyleSheet("color: #a0a0a0; font-weight: bold;")
        
        self.slider_strictness = QSlider(Qt.Orientation.Horizontal)
        self.slider_strictness.setRange(0, 15) 
        self.slider_strictness.setValue(self.current_strictness) 
        self.slider_strictness.valueChanged.connect(self.update_strictness_label)
        self.slider_strictness.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_strictness_label(self.current_strictness) 

        status_row.addWidget(self.lbl_strictness)
        status_row.addWidget(self.slider_strictness)
        status_row.addSpacing(30)
        
        self.lbl_dedupe_status = QLabel("Ready to scan.")
        self.lbl_dedupe_status.setStyleSheet("color: #0e639c; font-weight: bold;")
        self.btn_undo = QPushButton("Undo Last Action")
        self.btn_undo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_undo.setStyleSheet("QPushButton { background-color: transparent; border: 1px solid #d29922; color: #d29922; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 11px; } QPushButton:hover { background-color: rgba(210, 153, 34, 0.1); }")
        self.btn_undo.clicked.connect(self.undo_last_action)
        self.btn_undo.setVisible(False)
        
        self.shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.shortcut_undo.activated.connect(self.undo_last_action)
        
        status_row.addWidget(self.btn_undo)
        
        status_row.addWidget(self.lbl_dedupe_status)
        status_row.addStretch()

        command_layout.addLayout(status_row)
        dedupe_layout.addWidget(command_panel)

        self.pb_dedupe = QProgressBar()
        self.pb_dedupe.setFixedHeight(8)
        self.pb_dedupe.setTextVisible(False)
        self.pb_dedupe.setVisible(False)
        dedupe_layout.addWidget(self.pb_dedupe)

        content_split_layout = QHBoxLayout()

        self.dedupe_scroll = QScrollArea()
        self.dedupe_scroll.setWidgetResizable(True)
        self.dedupe_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.dedupe_scroll.setStyleSheet("QScrollArea { background-color: #1e1e1e; }")
        self.dedupe_scroll.verticalScrollBar().setSingleStep(20) # Smoother mouse wheel scrolling
        
        self.dedupe_content = QWidget()
        self.dedupe_content.setStyleSheet("QWidget { background-color: #1e1e1e; }")
        self.dedupe_content_layout = QVBoxLayout(self.dedupe_content)
        self.dedupe_content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.dedupe_content_layout.setSpacing(15) 
        
        self.dedupe_scroll.setWidget(self.dedupe_content)
        self.dedupe_scroll.verticalScrollBar().valueChanged.connect(self.on_dedupe_scroll)
        content_split_layout.addWidget(self.dedupe_scroll, stretch=3) 

        self.preview_panel = QFrame()
        self.preview_panel.setObjectName("PreviewPanel")
        self.preview_panel.setStyleSheet("#PreviewPanel { background-color: #252526; border-radius: 8px; border: 1px solid #3e3e42; }")
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        lbl_preview_title = QLabel("Group Comparison")
        lbl_preview_title.setStyleSheet("font-weight: bold; font-size: 15px; color: #ffffff;")
        preview_layout.addWidget(lbl_preview_title)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.preview_scroll.setStyleSheet("""
            QScrollArea { background-color: transparent; border: none; }
            QScrollBar:vertical { background: #1e1e1e; width: 12px; }
            QScrollBar::handle:vertical { background: #424242; border-radius: 6px; }
            QScrollBar::handle:vertical:hover { background: #4f4f4f; }
        """)

        self.preview_container = QWidget()
        self.preview_container.setStyleSheet("background-color: transparent;")
        
        self.preview_container_layout = QVBoxLayout(self.preview_container)
        self.preview_container_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.preview_container_layout.setSpacing(25)

        self.lbl_preview_placeholder = QLabel("Click an image to compare the group")
        self.lbl_preview_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview_placeholder.setStyleSheet("color: #666666; font-size: 14px;")
        self.preview_container_layout.addWidget(self.lbl_preview_placeholder)

        self.preview_scroll.setWidget(self.preview_container)
        preview_layout.addWidget(self.preview_scroll)

        content_split_layout.addWidget(self.preview_panel, stretch=7)
        dedupe_layout.addLayout(content_split_layout)
        main_layout.addWidget(self.tabs)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self.save_settings)
        
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        main_layout.addLayout(btn_layout)
        
        self.apply_styles()

    def apply_styles(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #cccccc; }
            #CommandPanel { background-color: #252526; border-radius: 8px; border: 1px solid #3e3e42; }
            QGroupBox { border: 1px solid #3e3e42; border-radius: 6px; margin-top: 15px; font-weight: bold; padding-top: 15px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #cccccc; }
            QLabel { color: #cccccc; }
            QLineEdit { background-color: #333337; border: 1px solid #454545; padding: 8px; color: white; border-radius: 4px; font-size: 13px; }
            QLineEdit:focus { border: 1px solid #0e639c; }
            QPushButton { background-color: #3e3e42; color: white; border-radius: 4px; padding: 6px 15px; font-weight: bold; border: none; }
            QPushButton:hover:!disabled { background-color: #505050; }
            QComboBox { background-color: #252526; color: white; border: 1px solid #3e3e42; border-radius: 3px; padding: 5px; min-width: 120px; }
            QTabBar::tab { background: #252526; color: #a0a0a0; padding: 10px 25px; border: 1px solid #3e3e42; border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; font-weight: bold; font-size: 13px; }
            QTabBar::tab:selected { background: #1e1e1e; color: #ffffff; border-top: 3px solid #0e639c; }
            QScrollArea { border: 1px solid #3e3e42; background-color: #1e1e1e; }
            QProgressBar { border: none; background-color: #1e1e1e; border-radius: 4px; } 
            QProgressBar::chunk { background-color: #0e639c; border-radius: 4px; }
        """)
        self.btn_save.setStyleSheet("QPushButton { background-color: #0e639c; color: white; } QPushButton:hover { background-color: #1177bb; }")
        self.btn_scan_dupes.setStyleSheet("QPushButton { font-size: 13px; background-color: #0e639c; color: white; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #1177bb; }")
        self.btn_auto_delete.setStyleSheet("QPushButton { font-size: 13px; background-color: #a31515; color: white; border-radius: 4px; font-weight: bold; } QPushButton:hover:!disabled { background-color: #d13438; } QPushButton:disabled { background-color: #333333; color: #666666; }")

    def update_strictness_label(self, val):
        if val == 0: text = "Exact Matches Only (0 diffs)"
        elif val <= 5: text = f"Balanced ({val} diffs allowed)"
        else: text = f"Loose ({val} diffs allowed)"
        self.lbl_strictness.setText(f"Strictness: {text}")

    def on_scale_changed(self, text):
        if text == "Custom...":
            val, ok = QInputDialog.getInt(
                self, 
                "Custom UI Scale", 
                "Enter UI Scale percentage (e.g. 74):", 
                100, 40, 400, 1
            )
            if ok:
                custom_scale_str = str(val / 100.0)
                custom_text = f"{val}%"
                
                if custom_text not in self.scale_map:
                    self.scale_map[custom_text] = custom_scale_str
                    self.combo_scale.insertItem(self.combo_scale.count() - 1, custom_text)
                
                self.combo_scale.setCurrentText(custom_text)
                self._last_scale_text = custom_text
            else:
                self.combo_scale.setCurrentText(self._last_scale_text)
        else:
            self._last_scale_text = text

    def keyPressEvent(self, event):
        """Intercepts Arrow Keys to navigate the duplicate grid instantly without lag."""
        if self.tabs.currentIndex() != 2 or not self.nav_groups:
            super().keyPressEvent(event)
            return

        focus_widget = QApplication.focusWidget()
        if not isinstance(focus_widget, FocusableClickableLabel):
            super().keyPressEvent(event)
            return

        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Down):
            
            current_g, current_i = -1, -1
            for g_idx, group in enumerate(self.nav_groups):
                if focus_widget in group:
                    current_g = g_idx
                    current_i = group.index(focus_widget)
                    break

            if current_g == -1:
                super().keyPressEvent(event)
                return

            def try_focus(g, i):
                try:
                    if 0 <= g < len(self.nav_groups) and 0 <= i < len(self.nav_groups[g]):
                        w = self.nav_groups[g][i]
                        if w.isVisible():
                            w.setFocus()
                            return True
                except RuntimeError:
                    pass
                return False

            if event.key() == Qt.Key.Key_Right:
                if not try_focus(current_g, current_i + 1):
                    try_focus(current_g + 1, 0)
                event.accept()
                
            elif event.key() == Qt.Key.Key_Left:
                if not try_focus(current_g, current_i - 1):
                    if current_g > 0:
                        try_focus(current_g - 1, len(self.nav_groups[current_g - 1]) - 1)
                event.accept()
                
            elif event.key() == Qt.Key.Key_Down:
                for next_g in range(current_g + 1, len(self.nav_groups)):
                    target_i = min(current_i, len(self.nav_groups[next_g]) - 1)
                    if try_focus(next_g, target_i):
                        break
                event.accept()
                
            elif event.key() == Qt.Key.Key_Up:
                for prev_g in range(current_g - 1, -1, -1):
                    target_i = min(current_i, len(self.nav_groups[prev_g]) - 1)
                    if try_focus(prev_g, target_i):
                        break
                event.accept()
        else:
            super().keyPressEvent(event)

    def on_dedupe_scroll(self, scroll_value):
        """Detects which duplicate group is currently visible and updates the preview."""
        if not self.current_duplicate_groups:
            return

        for idx in range(self.dedupe_content_layout.count()):
            widget = self.dedupe_content_layout.itemAt(idx).widget()
            
            if widget and widget.isVisible():
                if widget.y() + (widget.height() * 0.4) > scroll_value:
                    
                    group_idx = widget.property("group_index")
                    first_img = widget.property("first_image")
                    
                    if first_img and getattr(self, 'active_preview_group', -1) != group_idx:
                        self.active_preview_group = group_idx
                        
                        # Debounce the heavy image loading so scrolling doesn't lag
                        if hasattr(self, '_preview_timer'):
                            self._preview_timer.stop()
                        else:
                            self._preview_timer = QTimer(self)
                            self._preview_timer.setSingleShot(True)
                        
                        try:
                            self._preview_timer.timeout.disconnect()
                        except TypeError:
                            pass # Not connected yet
                            
                        self._preview_timer.timeout.connect(lambda p=first_img: self.show_preview(p))
                        self._preview_timer.start(150) # Wait 150ms after scroll settles
                    break

    def on_thumbnail_focused(self, file_path, widget):
        """Triggered automatically when the keyboard focus lands on an image."""
        self.show_preview(file_path)
        self.dedupe_scroll.ensureWidgetVisible(widget, 50, 100)

    def show_preview(self, file_path):
        if not os.path.exists(file_path): 
            return
            
        self.current_preview_path = file_path
        
        target_group = None
        for group_data in self.current_duplicate_groups:
            items = group_data[0]
            if any(item['path'] == file_path for item in items):
                target_group = items
                break
        
        if not target_group:
            target_group = [{'path': file_path}]
            
        for i in reversed(range(self.preview_container_layout.count())):
            w = self.preview_container_layout.itemAt(i).widget()
            if w: 
                w.setParent(None)
                w.deleteLater()

        # Determine aspect ratio of the first image to decide grid columns
        COLS = 2
        if target_group:
            first_path = target_group[0]['path']
            if os.path.exists(first_path):
                reader = QImageReader(first_path)
                orig_size = reader.size()
                if orig_size.isValid():
                    # If height is greater than width, it's portrait
                    if orig_size.height() > orig_size.width():
                        COLS = 3

        # Fill the full panel area
        grid_widget = QWidget()
        grid_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        grid = QGridLayout(grid_widget)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)

        INFO_H = 32

        for index, item in enumerate(target_group):

            path = item['path']
            if not os.path.exists(path): continue

            row, col = divmod(index, COLS)

            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(2)

            lbl_img = ResizableImageLabel()
            
            reader = QImageReader(path)
            orig_size = reader.size()
            if orig_size.isValid():
                # Load a high-res version into memory for the ResizableImageLabel to scale down cleanly
                reader.setScaledSize(orig_size.scaled(1200, 1200, Qt.AspectRatioMode.KeepAspectRatio))
                img = reader.read()
                if not img.isNull():
                    lbl_img.setPixmap(QPixmap.fromImage(img))

            is_selected = (path == file_path)
            border_color = "#00a2ff" if is_selected else "#3e3e42"
            
            # Create a frame around the image so the border covers the max layout space
            frame_img = QFrame()
            frame_img.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            frame_img.setStyleSheet(f"background-color: #1e1e1e; border: 2px solid {border_color}; border-radius: 4px;")
            frame_layout = QVBoxLayout(frame_img)
            frame_layout.setContentsMargins(0, 0, 0, 0)
            frame_layout.addWidget(lbl_img)

            res_text = f"{orig_size.width()}x{orig_size.height()}" if orig_size.isValid() else "?"
            size_mb = os.path.getsize(path) / (1024 * 1024)
            filename = os.path.basename(path)
            text_color = "#00a2ff" if is_selected else "#cccccc"

            lbl_info = QLabel(
                f"<b style='color:{text_color};'>#{index+1} {filename}</b> "
                f"<span style='color:#777777; font-size:11px;'>{res_text} | {size_mb:.2f} MB</span>"
            )
            lbl_info.setWordWrap(False)
            lbl_info.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            lbl_info.setFixedHeight(INFO_H)
            lbl_info.setStyleSheet("font-size: 12px; padding-left: 4px;")

            cell_layout.addWidget(frame_img, stretch=1)
            cell_layout.addWidget(lbl_info)
            
            grid.addWidget(cell, row, col)
            grid.setRowStretch(row, 1)
            grid.setColumnStretch(col, 1)

        self.preview_container_layout.addWidget(grid_widget)

    def on_tab_changed(self, index):
        tab_name = self.tabs.tabText(index)
        
        if tab_name in ["Tag Manager", "Image Dedup", "Video Dedup"]:
            settings = QSettings("MediaNest", "AppConfig")
            
            if not settings.value("db_folder_path"):
                setup_window = FirstTimeSetupDialog(self)
                
                if setup_window.exec() == QDialog.DialogCode.Accepted:
                    self.load_config()
                    self.db_path_input.setText(self.current_db_folder)
                else:
                    self.tabs.setCurrentIndex(1) 
                    return

        if tab_name == "Tag Manager":
            if self.tab_tag_manager is None:
                self.tabs.setTabIcon(index, QIcon(os.path.join(self.asset_base_dir, "assets", "uisvg", "loading.svg")))
                self.tabs.setTabText(index, "Loading...")
                QApplication.processEvents()
                
                self.tab_tag_manager = TagManagerTab(self)
                self.tabs.removeTab(index)
                self.tabs.insertTab(index, self.tab_tag_manager, "Tag Manager")
                self.tabs.setCurrentIndex(index)
            
            QTimer.singleShot(20, self.tab_tag_manager.refresh_global_tags)
            QTimer.singleShot(20, self.tab_tag_manager.refresh_tagless_inbox)

        elif tab_name == "Image Dedup":
            self._setup_dedupe_tag_completer()

        elif tab_name == "Video Dedup":
            if self.tab_video_dedup is None:
                self.tabs.setTabIcon(index, QIcon(os.path.join(self.asset_base_dir, "assets", "uisvg", "loading.svg")))
                self.tabs.setTabText(index, "Loading...")
                QApplication.processEvents()
                
                self.tab_video_dedup = VideoDedupTab(self)
                self.tabs.removeTab(index)
                self.tabs.insertTab(index, self.tab_video_dedup, "Video Dedup")
                self.tabs.setCurrentIndex(index)

        elif tab_name == "Pagination":
            if self.tab_pagination is None:
                self.tabs.setTabIcon(index, QIcon(os.path.join(self.asset_base_dir, "assets", "uisvg", "loading.svg")))
                self.tabs.setTabText(index, "Loading...")
                QApplication.processEvents()
                
                self.tab_pagination = PaginationTab(self)
                self.tabs.removeTab(index)
                self.tabs.insertTab(index, self.tab_pagination, "Pagination")
                self.tabs.setCurrentIndex(index)

    def clear_preview(self):
        self.current_preview_path = ""
        
        for i in reversed(range(self.preview_container_layout.count())):
            w = self.preview_container_layout.itemAt(i).widget()
            if w: 
                w.setParent(None)
                w.deleteLater()
            
        self.lbl_preview_placeholder = QLabel("Click an image to compare the group")
        self.lbl_preview_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview_placeholder.setStyleSheet("color: #666666; font-size: 14px;")
        self.preview_container_layout.addWidget(self.lbl_preview_placeholder)


    def _setup_dedupe_tag_completer(self):
        """Load tags directly from the DB and attach autocomplete to the target tag input."""
        if self.dedupe_target_tag_input.completer():
            return  # Already set up

        # Get db folder — from instance var or directly from QSettings
        db_folder = self.current_db_folder
        if not db_folder:
            db_folder = QSettings("MediaNest", "AppConfig").value("db_folder_path", "", type=str)

        db_file = os.path.join(db_folder, "library.db") if db_folder else ""
        if not db_file or not os.path.exists(db_file):
            print(f"[Dedup Autocomplete] DB not found at: {db_file}")
            return

        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT tag_name FROM Tags")  # column is 'tag_name'
            all_tags = sorted(set(row[0] for row in cursor.fetchall() if row[0]))
            conn.close()
        except Exception as e:
            print(f"[Dedup Autocomplete] Failed to load tags: {e}")
            return

        if not all_tags:
            print("[Dedup Autocomplete] No tags found in DB.")
            return

        print(f"[Dedup Autocomplete] Loaded {len(all_tags)} tags.")

        local_model = QStringListModel(all_tags, self)
        completer = QCompleter(local_model, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setMaxVisibleItems(10)
        completer.popup().setStyleSheet("""
            QListView {
                background-color: #252526;
                color: white;
                border: 1px solid #3e3e42;
                font-size: 13px;
                padding: 5px;
            }
            QListView::item {
                padding: 6px;
                border-radius: 4px;
            }
            QListView::item:hover, QListView::item:selected {
                background-color: #007acc;
            }
        """)
        self.dedupe_target_tag_input.setCompleter(completer)

    def start_dedupe_scan(self, is_auto_rescan=False):
        if not is_auto_rescan: self.auto_delete_mode = "safe"

        if not self.current_db_folder: 
            QMessageBox.warning(self, "No Database Folder", "Please select your 'Library Folder' in the Database tab first, then hit Save Settings!")
            return

        db_file = os.path.join(self.current_db_folder, "library.db")
        if not os.path.exists(db_file): 
            QMessageBox.critical(self, "Database Missing", f"Could not find library.db at:\n\n{db_file}\n\nPlease check your folder path in the Database tab.")
            return

        self.undo_trash_dir = os.path.join(self.current_db_folder, "UndoTrash")
        if not os.path.exists(self.undo_trash_dir):
            try:
                os.makedirs(self.undo_trash_dir)
            except Exception as e:
                print(f"Failed to create UndoTrash: {e}")
                self.undo_trash_dir = ""

        self.btn_scan_dupes.setEnabled(False)
        self.btn_scan_dupes.setIcon(QIcon(os.path.join(self.asset_base_dir, "assets", "uisvg", "loading.svg")))
        self.btn_scan_dupes.setText("Scanning...")
        self.pb_dedupe.setVisible(True)
        self.pb_dedupe.setValue(0)
        
        self.btn_auto_delete.setEnabled(False)
        self.dedupe_search_bar.setEnabled(False)
        self.clear_preview() 
        self.thumb_labels_map.clear()
        self.nav_groups.clear()
        
        self.render_queue = []
        for i in reversed(range(self.dedupe_content_layout.count())):
            w = self.dedupe_content_layout.itemAt(i).widget()
            if w: w.setParent(None)

        target_tag = self.dedupe_target_tag_input.text().strip()
        self.dedupe_worker = DeduplicationWorker(db_file, self.slider_strictness.value(), target_tag)
        self.dedupe_worker.progress_signal.connect(self.update_dedupe_progress)
        self.dedupe_worker.status_signal.connect(self.handle_worker_status) 
        self.dedupe_worker.duplicates_found.connect(self.render_duplicates_ui)
        self.dedupe_worker.finished_signal.connect(self.dedupe_finished)
        self.dedupe_worker.start()

    def handle_worker_status(self, text):
        self.lbl_dedupe_status.setText(text)
        if text.startswith("Error:"):
            QMessageBox.critical(self, "Scanner Crash", f"The background scanner crashed with the following error:\n\n{text}")

    def update_dedupe_progress(self, current, total):
        if total > 0:
            self.pb_dedupe.setMaximum(total)
            self.pb_dedupe.setValue(current)

    def dedupe_finished(self):
        self.btn_scan_dupes.setEnabled(True)
        self.btn_scan_dupes.setIcon(QIcon())
        self.btn_scan_dupes.setText("Scan Library")
        self.pb_dedupe.setVisible(False)

    def render_duplicates_ui(self, duplicate_groups):
        self.current_duplicate_groups = duplicate_groups 

        if not duplicate_groups:
            self.lbl_dedupe_status.setText("Library is clean! No duplicates found.")
            return

        self.btn_auto_delete.setEnabled(True)
        self.dedupe_search_bar.setEnabled(True)

        if self.auto_delete_mode == "safe": self.btn_auto_delete.setText("Auto-Delete Low Res")
        else: self.btn_auto_delete.setText("Auto-Delete Low MB (Same Res)")

        self.render_queue = list(enumerate(duplicate_groups))
        self.total_render_items = len(self.render_queue)
        self.pb_dedupe.setVisible(True)
        self.pb_dedupe.setMaximum(self.total_render_items)
        self.pb_dedupe.setValue(0)
        
        all_paths = []
        for _, group_data in self.render_queue:
            for item in group_data[0]: all_paths.append(item['path'])
            
        self.thumb_worker = ThumbnailWorker(all_paths)
        self.thumb_worker.thumb_ready.connect(self.apply_thumbnail)
        self.thumb_worker.start()
        
        self.render_next_batch()

    def apply_thumbnail(self, path, qimage, res_text, size_mb):
        if path in self.thumb_labels_map:
            widgets = self.thumb_labels_map[path]
            try:
                widgets['thumb'].setPixmap(QPixmap.fromImage(qimage))
                widgets['info'].setText(f"{res_text}  |  {size_mb} MB")
            except RuntimeError:
                pass # Widget has been deleted by user action (e.g. Auto Delete)

    def render_next_batch(self):
        if not self.render_queue:
            self.lbl_dedupe_status.setText(f"Done! Displaying {self.total_render_items} duplicate groups.")
            self.pb_dedupe.setVisible(False)
            
            self.on_dedupe_scroll(self.dedupe_scroll.verticalScrollBar().value())
            return

        i, group_data = self.render_queue.pop(0)

        rendered_count = self.total_render_items - len(self.render_queue)
        self.pb_dedupe.setValue(rendered_count)
        self.lbl_dedupe_status.setText(f"Loading images... {rendered_count} / {self.total_render_items}")

        group_card, nav_group_row = self.create_group_card(i, group_data)
        
        if nav_group_row:
            self.nav_groups.append(nav_group_row)

        self.dedupe_content_layout.addWidget(group_card)
        QTimer.singleShot(5, self.render_next_batch)

    def create_group_card(self, i, group_data):
        group_items, group_tags, avg_conf = group_data 

        group_card = QFrame()
        group_card.setObjectName("GroupCard")
        group_card.setProperty("search_tags", group_tags)
        group_card.setProperty("group_index", i) 
        group_card.setProperty("first_image", group_items[0]['path'])
        group_card.setStyleSheet("#GroupCard { background-color: #2d2d30; border-radius: 8px; border: 1px solid #3e3e42; }")
        
        card_main_layout = QVBoxLayout(group_card)
        card_main_layout.setContentsMargins(15, 15, 15, 15)

        header_layout = QHBoxLayout()
        
        title_layout = QVBoxLayout()
        lbl_title = QLabel(f"Duplicate Group #{i+1}")
        lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
        
        lbl_conf = QLabel(f"Confidence: {avg_conf}%")
        conf_color = "#3fb950" if avg_conf > 90 else "#d29922"
        lbl_conf.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {conf_color}; background-color: rgba(0,0,0,0.2); padding: 3px 6px; border-radius: 4px;")
        
        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_conf, alignment=Qt.AlignmentFlag.AlignLeft)
        title_layout.setSpacing(4)
        
        btn_ignore = QPushButton("Mark as 'Not Duplicates'")
        btn_ignore.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ignore.setStyleSheet("QPushButton { background-color: transparent; border: 1px solid #3fb950; color: #3fb950; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 11px; } QPushButton:hover { background-color: rgba(63, 185, 80, 0.1); }")
        
        btn_delete_all = QPushButton("Delete All")
        btn_delete_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_delete_all.setStyleSheet("QPushButton { background-color: transparent; border: 1px solid #a31515; color: #a31515; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 11px; } QPushButton:hover { background-color: rgba(163, 21, 21, 0.1); }")
        
        btn_auto_del = QPushButton("Auto Delete")
        btn_auto_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_auto_del.setStyleSheet("QPushButton { background-color: transparent; border: 1px solid #d29922; color: #d29922; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 11px; } QPushButton:hover { background-color: rgba(210, 153, 34, 0.1); }")
        
        btn_layout = QVBoxLayout()
        btn_layout.addWidget(btn_auto_del)
        btn_layout.addWidget(btn_delete_all)
        btn_layout.addWidget(btn_ignore)
        btn_layout.setSpacing(4)
        
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        header_layout.addLayout(btn_layout)
        card_main_layout.addLayout(header_layout)
        
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #3e3e42;")
        card_main_layout.addWidget(line)

        COLS = 3
        group_images_grid = QGridLayout()
        group_images_grid.setSpacing(10)
        has_checkboxes = len(group_items) >= 3
        checkbox_refs = []
        nav_group_row = []

        for idx, item in enumerate(group_items):
            file_path = item['path']
            row, col = divmod(idx, COLS)

            item_widget = QWidget()
            item_layout = QVBoxLayout(item_widget)
            item_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            item_layout.setContentsMargins(5, 5, 5, 5)

            thumb_layout = QVBoxLayout()

            lbl_thumb = FocusableClickableLabel(file_path)
            lbl_thumb.clicked.connect(self.show_preview)
            lbl_thumb.focused.connect(self.on_thumbnail_focused)
            lbl_thumb.setFixedSize(90, 90)
            lbl_thumb.setStyleSheet("background-color: #1e1e1e; border: 1px solid #454545; border-radius: 4px;")
            lbl_thumb.setText("Loading...")
            lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)

            nav_group_row.append(lbl_thumb)
            thumb_layout.addWidget(lbl_thumb)

            if has_checkboxes:
                cb = QCheckBox("Select Exception")
                cb.setCursor(Qt.CursorShape.PointingHandCursor)
                cb.setProperty("hash_val", item['hash'])
                cb.item_widget = item_widget
                checkbox_refs.append(cb)
                thumb_layout.addWidget(cb)

            lbl_name = QLabel(os.path.basename(file_path))
            lbl_name.setWordWrap(True)
            lbl_name.setStyleSheet("font-weight: bold; margin-top: 4px; font-size: 12px; color: #e0e0e0;")

            lbl_info = QLabel("Loading info...")
            lbl_info.setStyleSheet("color: #858585; font-size: 11px;")

            self.thumb_labels_map[file_path] = {'thumb': lbl_thumb, 'info': lbl_info}

            btn_del = QPushButton("Recycle Bin")
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setStyleSheet("QPushButton { background-color: #a31515; color: white; padding: 6px; margin-top: 4px; border-radius: 4px; } QPushButton:hover { background-color: #d13438; }")
            btn_del.clicked.connect(lambda checked, p=file_path, w=item_widget, gd=group_data, cbs=checkbox_refs, gc=group_card: self.delete_duplicate(p, w, gd, cbs, gc))

            item_layout.addLayout(thumb_layout)
            item_layout.addWidget(lbl_name)
            item_layout.addWidget(lbl_info)
            item_layout.addWidget(btn_del)
            group_images_grid.addWidget(item_widget, row, col)

        card_main_layout.addLayout(group_images_grid)
        
        btn_ignore.clicked.connect(lambda checked, gc=group_card, gd=group_data, cbs=checkbox_refs: self.mark_not_duplicates(gc, gd, cbs))
        btn_delete_all.clicked.connect(lambda checked, gc=group_card, gd=group_data: self.delete_all_duplicates(gc, gd))
        btn_auto_del.clicked.connect(lambda checked, gc=group_card, gd=group_data, cbs=checkbox_refs: self.auto_delete_group(gc, gd, cbs))
        
        return group_card, nav_group_row

    def push_undo_action(self, snapshot):
        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > 2:
            oldest = self.undo_stack.pop(0)
            if oldest['type'] == 'delete':
                for f in oldest['files']:
                    try:
                        if os.path.exists(f['trash_path']):
                            send2trash(f['trash_path'])
                    except Exception as e:
                        print(f"Failed to send to trash from undo stack: {e}")
        
        self.btn_undo.setVisible(True)
        self.btn_undo.setText(f"Undo Last Action ({len(self.undo_stack)})")

    def undo_last_action(self):
        if not self.undo_stack:
            return
            
        snapshot = self.undo_stack.pop()
        
        db_file = os.path.join(self.current_db_folder, "library.db")
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        if snapshot['type'] == 'delete':
            for f in snapshot['files']:
                if os.path.exists(f['trash_path']):
                    try:
                        shutil.move(f['trash_path'], f['original_path'])
                        row = f['db_row']
                        if row:
                            placeholders = ','.join(['?'] * len(row))
                            cursor.execute(f"INSERT OR REPLACE INTO Images VALUES ({placeholders})", row)
                    except Exception as e:
                        print(f"Failed to restore file {f['original_path']}: {e}")
        elif snapshot['type'] == 'ignore':
            for h1, h2 in snapshot['ignored_pairs']:
                cursor.execute("DELETE FROM IgnoredPairs WHERE (hash1 = ? AND hash2 = ?) OR (hash1 = ? AND hash2 = ?)", (h1, h2, h2, h1))
        
        conn.commit()
        conn.close()
        
        card_index = snapshot['card_index']
        group_data = snapshot['group_data_snapshot']
        group_card_ref = snapshot.get('group_card_ref')
        
        if not snapshot.get('is_group_removed', True):
            if group_card_ref:
                group_card_ref.setParent(None)
                group_card_ref.deleteLater()
                if snapshot['current_group_data'] in self.current_duplicate_groups:
                    self.current_duplicate_groups.remove(snapshot['current_group_data'])
        
        if group_data not in self.current_duplicate_groups:
            self.current_duplicate_groups.insert(card_index, group_data)
            
        new_card, nav_group = self.create_group_card(card_index, group_data)
        
        if nav_group:
            self.nav_groups.insert(card_index, nav_group)
            
        self.dedupe_content_layout.insertWidget(card_index, new_card)
        
        if not self.undo_stack:
            self.btn_undo.setVisible(False)
        else:
            self.btn_undo.setText(f"Undo Last Action ({len(self.undo_stack)})")
            
        self.lbl_dedupe_status.setText("Action undone successfully.")

    def remove_group_and_select_next(self, group_card):
        self.dedupe_scroll.setFocus()
        scroll_bar = self.dedupe_scroll.verticalScrollBar()
        current_scroll = scroll_bar.value()
        
        is_previewed = (group_card.property("group_index") == getattr(self, 'active_preview_group', -1))
        index = self.dedupe_content_layout.indexOf(group_card)
        
        group_card.setParent(None)
        group_card.deleteLater()
        
        QTimer.singleShot(0, lambda: scroll_bar.setValue(current_scroll))
        
        if is_previewed:
            self.clear_preview()
            
            next_widget = None
            if index < self.dedupe_content_layout.count():
                item = self.dedupe_content_layout.itemAt(index)
                if item: next_widget = item.widget()
            
            if not next_widget and index - 1 >= 0:
                item = self.dedupe_content_layout.itemAt(index - 1)
                if item: next_widget = item.widget()
                
            if next_widget:
                first_img = next_widget.property("first_image")
                group_idx = next_widget.property("group_index")
                if first_img:
                    self.active_preview_group = group_idx
                    self.show_preview(first_img)

    def mark_not_duplicates(self, group_card, group_data, checkboxes):
        group_items = group_data[0]
        
        db_file = os.path.join(self.current_db_folder, "library.db")
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        all_hashes = [item['hash'] for item in group_items]
        pairs_to_ignore = []

        selected_hashes = []
        if checkboxes:
            for cb in checkboxes:
                try:
                    if cb.isChecked() and cb.isVisible():
                        selected_hashes.append(cb.property("hash_val"))
                except RuntimeError:
                    continue 

        if not selected_hashes:
            for i in range(len(all_hashes)):
                for j in range(i + 1, len(all_hashes)):
                    pairs_to_ignore.append(tuple(sorted((all_hashes[i], all_hashes[j]))))
        else:
            for selected in selected_hashes:
                for other in all_hashes:
                    if selected != other:
                        pairs_to_ignore.append(tuple(sorted((selected, other))))
        
        for h1, h2 in set(pairs_to_ignore):
            cursor.execute("INSERT OR IGNORE INTO IgnoredPairs (hash1, hash2) VALUES (?, ?)", (h1, h2))
            
        conn.commit()
        conn.close()
        
        snapshot_group_data = copy.deepcopy(group_data)
        card_index = self.dedupe_content_layout.indexOf(group_card)
        
        if 'selected_hashes' in locals() and selected_hashes:
            remaining_items = [item for item in group_items if item['hash'] not in selected_hashes]
            if len(remaining_items) >= 2:
                # Modify in place so the tuple reference remains intact
                group_items.clear()
                group_items.extend(remaining_items)
                
                self.dedupe_scroll.setFocus()
                scroll_bar = self.dedupe_scroll.verticalScrollBar()
                current_scroll = scroll_bar.value()
                
                for cb in checkboxes:
                    try:
                        if cb.isChecked() and cb.isVisible() and hasattr(cb, 'item_widget'):
                            w = cb.item_widget
                            w.setParent(None)
                            w.deleteLater()
                        elif len(remaining_items) <= 2:
                            cb.setVisible(False)
                    except RuntimeError:
                        pass
                
                QTimer.singleShot(0, lambda: scroll_bar.setValue(current_scroll))
                
                is_previewed = (group_card.property("group_index") == getattr(self, 'active_preview_group', -1))
                if is_previewed:
                    self.clear_preview()
                    if len(group_items) > 0:
                        self.show_preview(group_items[0]['path'])
                    
                self.push_undo_action({
                    'type': 'ignore',
                    'ignored_pairs': set(pairs_to_ignore),
                    'group_data_snapshot': snapshot_group_data,
                    'card_index': card_index,
                    'is_group_removed': False,
                    'group_card_ref': group_card
                })
                
                return
        
        if group_data in self.current_duplicate_groups:
            self.current_duplicate_groups.remove(group_data)
        
        self.remove_group_and_select_next(group_card)
        
        self.push_undo_action({
            'type': 'ignore',
            'ignored_pairs': set(pairs_to_ignore),
            'group_data_snapshot': snapshot_group_data,
            'card_index': card_index,
            'is_group_removed': True,
            'group_card_ref': group_card
        })

    def auto_delete_group(self, group_card, group_data, checkboxes=None):
        group_items = group_data[0]
        
        checked_hashes = set()
        if checkboxes:
            for cb in checkboxes:
                try:
                    if cb.isChecked() and cb.isVisible():
                        checked_hashes.add(cb.property("hash_val"))
                except RuntimeError:
                    continue
        
        best_file = None
        best_score = -1

        extension_scores = {'.webp': 3, '.png': 2, '.jpg': 1, '.jpeg': 1, '.bmp': 0}
        def get_image_score(path):
            ext = os.path.splitext(path)[1].lower()
            return extension_scores.get(ext, 0)

        files_to_delete = []

        for item in group_items:
            if item['hash'] in checked_hashes:
                continue
                
            path = item['path']
            if not os.path.exists(path): continue
            
            size = QImageReader(path).size()
            res_score = (size.width() * size.height()) if size.isValid() else 0

            if res_score > best_score:
                if best_file: files_to_delete.append(best_file)
                best_score = res_score
                best_file = path
            elif res_score == best_score:
                if best_file and os.path.getsize(path) > os.path.getsize(best_file):
                    files_to_delete.append(best_file)
                    best_file = path
                elif best_file and os.path.getsize(path) == os.path.getsize(best_file):
                    if get_image_score(path) > get_image_score(best_file):
                        files_to_delete.append(best_file)
                        best_file = path
                    else:
                        files_to_delete.append(path)
                else:
                    files_to_delete.append(path)
            else:
                files_to_delete.append(path)

        if not files_to_delete:
            return

        proceed = False
        if getattr(self, 'skip_group_auto_delete_confirm', False):
            proceed = True
        else:
            msgBox = QMessageBox(self)
            msgBox.setWindowTitle("Confirm Auto Delete")
            msgBox.setText(f"Found {len(files_to_delete)} lower quality duplicate(s) in this group.\n\nAre you sure you want to move them to the Recycle Bin?")
            msgBox.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
            cb = QCheckBox("Don't ask again in this session")
            msgBox.setCheckBox(cb)
            
            reply = msgBox.exec()
            if reply == QMessageBox.StandardButton.Yes:
                proceed = True
                if cb.isChecked():
                    self.skip_group_auto_delete_confirm = True

        if proceed:
            snapshot_group_data = copy.deepcopy(group_data)
            card_index = self.dedupe_content_layout.indexOf(group_card)
            
            db_file = os.path.join(self.current_db_folder, "library.db")
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            deleted_files_info = []
            
            for path in files_to_delete:
                cursor.execute("SELECT * FROM Images WHERE file_path = ?", (path,))
                row = cursor.fetchone()
                if row and os.path.exists(path):
                    trash_path = os.path.join(self.undo_trash_dir, str(uuid.uuid4()) + os.path.splitext(path)[1])
                    try:
                        shutil.move(path, trash_path)
                        deleted_files_info.append({
                            'original_path': path, 'trash_path': trash_path, 'db_row': row
                        })
                        cursor.execute("DELETE FROM Images WHERE file_path = ?", (path,))
                    except Exception as e:
                        print(f"Failed to move {path} to undo trash: {e}")
            
            conn.commit()
            conn.close()
            
            if group_data in self.current_duplicate_groups:
                self.current_duplicate_groups.remove(group_data)
            
            self.remove_group_and_select_next(group_card)
            
            self.push_undo_action({
                'type': 'delete',
                'files': deleted_files_info,
                'group_data_snapshot': snapshot_group_data,
                'card_index': card_index,
                'is_group_removed': True,
                'group_card_ref': group_card
            })


    def filter_duplicates(self, text):
        search_text = text.lower().strip()
        for i in range(self.dedupe_content_layout.count()):
            widget = self.dedupe_content_layout.itemAt(i).widget()
            if widget:
                hidden_tags = widget.property("search_tags")
                if not search_text or (hidden_tags and search_text in hidden_tags):
                    widget.show()
                else:
                    widget.hide()

    def auto_delete_low_res(self):
        if not self.current_duplicate_groups: return

        files_to_delete = []
        extension_scores = {'.webp': 3, '.png': 2, '.jpg': 1, '.jpeg': 1, '.bmp': 0}

        def get_image_score(path):
            ext = os.path.splitext(path)[1].lower()
            return extension_scores.get(ext, 0)

        for group_data in self.current_duplicate_groups:
            group_items, _, _ = group_data 
            
            if self.auto_delete_mode == "safe":
                resolutions = set()
                for item in group_items:
                    path = item['path']
                    if os.path.exists(path):
                        size = QImageReader(path).size()
                        if size.isValid(): resolutions.add(f"{size.width()}x{size.height()}")
                
                if len(resolutions) == 1: continue 

                best_file = None
                best_score = -1

                for item in group_items:
                    path = item['path']
                    if not os.path.exists(path): continue
                    
                    size = QImageReader(path).size()
                    score = (size.width() * size.height()) if size.isValid() else 0

                    if score > best_score:
                        if best_file: files_to_delete.append(best_file)
                        best_score = score
                        best_file = path
                    elif score == best_score:
                        if best_file and os.path.getsize(path) > os.path.getsize(best_file):
                            files_to_delete.append(best_file)
                            best_file = path
                        else:
                            files_to_delete.append(path)
                    else:
                        files_to_delete.append(path)

            elif self.auto_delete_mode == "aggressive":
                best_file = None
                best_size = -1
                best_ext_score = -1

                for item in group_items:
                    path = item['path']
                    if not os.path.exists(path): continue
                    
                    file_size = os.path.getsize(path)
                    ext_score = get_image_score(path)

                    if file_size > best_size or (abs(file_size - best_size) < 100000 and ext_score > best_ext_score):
                        if best_file: files_to_delete.append(best_file)
                        best_size = file_size
                        best_ext_score = ext_score
                        best_file = path
                    else:
                        files_to_delete.append(path)

        if not files_to_delete:
            if self.auto_delete_mode == "safe":
                self.auto_delete_mode = "aggressive"
                self.btn_auto_delete.setText("Auto-Delete Low MB (Same Res)")
                QMessageBox.information(self, "Phase 1 Complete", "All strictly low-resolution duplicates have been cleaned!\n\nThe button has now updated to Phase 2. Click it again to clean up duplicates that share the exact same resolution by keeping the largest/best file.")
            else:
                QMessageBox.information(self, "Fully Clean", "No remaining duplicates found to auto-delete.")
            return

        mode_text = "strictly lower resolution" if self.auto_delete_mode == "safe" else "lower quality (identical resolutions)"
        reply = QMessageBox.question(self, "Confirm Send to Recycle Bin", f"Found {len(files_to_delete)} {mode_text} duplicates.\n\nAre you sure you want to move them to the Recycle Bin?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.is_global_delete = True
            self.clear_preview() 
            self.delete_queue = files_to_delete
            self.total_to_delete = len(files_to_delete)
            self.deleted_count = 0
            self.btn_auto_delete.setEnabled(False)
            self.btn_scan_dupes.setEnabled(False)
            self.pb_dedupe.setVisible(True)
            self.pb_dedupe.setMaximum(self.total_to_delete)
            self.pb_dedupe.setValue(0)
            
            db_file = os.path.join(self.current_db_folder, "library.db")
            self.delete_conn = sqlite3.connect(db_file)
            self.delete_cursor = self.delete_conn.cursor()
            self.process_delete_batch()

    def process_delete_batch(self):
        if not self.delete_queue:
            self.delete_conn.commit()
            self.delete_conn.close()
            self.pb_dedupe.setVisible(False)
            
            if not getattr(self, 'skip_group_auto_delete_confirm', False) and getattr(self, 'is_global_delete', False):
                QMessageBox.information(self, "Success", f"Moved {self.deleted_count} files to the Recycle Bin!")
            
            if getattr(self, 'is_global_delete', False):
                if self.auto_delete_mode == "safe": self.auto_delete_mode = "aggressive"
                else: self.auto_delete_mode = "safe" 
                self.start_dedupe_scan(is_auto_rescan=True) 
            return

        chunk = self.delete_queue[:10]
        self.delete_queue = self.delete_queue[10:]

        for path in chunk:
            try:
                if os.path.exists(path): send2trash(path) 
                self.delete_cursor.execute("DELETE FROM Images WHERE file_path = ?", (path,))
                self.deleted_count += 1
            except Exception:
                pass

        self.delete_conn.commit()
        self.pb_dedupe.setValue(self.deleted_count)
        QTimer.singleShot(10, self.process_delete_batch)

    def delete_duplicate(self, file_path, widget_to_remove, group_data=None, checkbox_refs=None, group_card=None):
        reply = QMessageBox.question(self, "Confirm", f"Move this file to the Recycle Bin?\n{os.path.basename(file_path)}", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                snapshot_group_data = copy.deepcopy(group_data) if group_data else None
                card_index = self.dedupe_content_layout.indexOf(group_card) if group_card else -1
                
                db_file = os.path.join(self.current_db_folder, "library.db")
                conn = sqlite3.connect(db_file)
                cursor = conn.cursor()
                
                deleted_files_info = []
                cursor.execute("SELECT * FROM Images WHERE file_path = ?", (file_path,))
                row = cursor.fetchone()
                
                if row and os.path.exists(file_path):
                    trash_path = os.path.join(self.undo_trash_dir, str(uuid.uuid4()) + os.path.splitext(file_path)[1])
                    shutil.move(file_path, trash_path)
                    deleted_files_info.append({
                        'original_path': file_path, 'trash_path': trash_path, 'db_row': row
                    })
                    cursor.execute("DELETE FROM Images WHERE file_path = ?", (file_path,))
                    
                conn.commit()
                conn.close()
                
                is_previewed = group_card and (group_card.property("group_index") == getattr(self, 'active_preview_group', -1))
                if is_previewed:
                    self.clear_preview()
                
                self.dedupe_scroll.setFocus()
                scroll_bar = self.dedupe_scroll.verticalScrollBar()
                current_scroll = scroll_bar.value()
                
                widget_to_remove.setParent(None)
                widget_to_remove.deleteLater()
                
                QTimer.singleShot(0, lambda: scroll_bar.setValue(current_scroll))
                
                group_will_be_removed = False
                
                if group_data:
                    items_to_keep = [item for item in group_data[0] if item['path'] != file_path]
                    group_data[0].clear()
                    group_data[0].extend(items_to_keep)
                    
                    if len(group_data[0]) <= 2 and checkbox_refs:
                        for cb in checkbox_refs:
                            try:
                                cb.setVisible(False)
                            except RuntimeError:
                                pass
                                
                    if len(group_data[0]) < 2 and group_card:
                        group_will_be_removed = True
                        if group_data in self.current_duplicate_groups:
                            self.current_duplicate_groups.remove(group_data)
                        self.remove_group_and_select_next(group_card)
                    elif is_previewed and len(group_data[0]) > 0:
                        self.show_preview(group_data[0][0]['path'])
                
                if snapshot_group_data:
                    self.push_undo_action({
                        'type': 'delete',
                        'files': deleted_files_info,
                        'group_data_snapshot': snapshot_group_data,
                        'card_index': card_index,
                        'is_group_removed': group_will_be_removed,
                        'group_card_ref': group_card
                    })
                        
            except Exception as e:
                print(f"Delete duplicate error: {e}")

    def delete_all_duplicates(self, group_card, group_data):
        group_items = group_data[0]
        
        reply = QMessageBox.question(
            self, 
            "Confirm Delete All", 
            f"Are you sure you want to move ALL {len(group_items)} images in this group to the Recycle Bin?", 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            snapshot_group_data = copy.deepcopy(group_data)
            card_index = self.dedupe_content_layout.indexOf(group_card)
            
            db_file = os.path.join(self.current_db_folder, "library.db")
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            paths_to_delete = [item['path'] for item in group_items]
            deleted_files_info = []
            
            for path in paths_to_delete:
                try:
                    cursor.execute("SELECT * FROM Images WHERE file_path = ?", (path,))
                    row = cursor.fetchone()
                    if row and os.path.exists(path):
                        trash_path = os.path.join(self.undo_trash_dir, str(uuid.uuid4()) + os.path.splitext(path)[1])
                        shutil.move(path, trash_path)
                        deleted_files_info.append({
                            'original_path': path, 'trash_path': trash_path, 'db_row': row
                        })
                        cursor.execute("DELETE FROM Images WHERE file_path = ?", (path,))
                except Exception as e:
                    print(f"Failed to delete {path}: {e}")
                    
            conn.commit()
            conn.close()
                
            if group_data in self.current_duplicate_groups:
                self.current_duplicate_groups.remove(group_data)
                
            self.remove_group_and_select_next(group_card)
            
            self.push_undo_action({
                'type': 'delete',
                'files': deleted_files_info,
                'group_data_snapshot': snapshot_group_data,
                'card_index': card_index,
                'is_group_removed': True,
                'group_card_ref': group_card
            })

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Database Folder", self.current_db_folder)
        if folder: self.db_path_input.setText(os.path.normpath(folder))

    def save_settings(self):
        
        new_folder = self.db_path_input.text().strip()
        scale_text = self.combo_scale.currentText()
        if scale_text == "Custom...":
            scale_text = getattr(self, '_last_scale_text', "100% (Default)")
        new_scale_val = self.scale_map.get(scale_text, "1.0")
        new_strictness = self.slider_strictness.value() 
        config_changed = False
        
        settings = QSettings("MediaNest", "AppConfig")
        if new_folder:
            settings.setValue("db_folder_path", new_folder)
        else:
            settings.remove("db_folder_path")

        try:
            config = {}
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path, "r") as f: 
                        config = json.load(f)
                except json.JSONDecodeError:
                    config = {}
            
            if new_folder != self.current_db_folder:
                config["db_folder"] = new_folder
                self.current_db_folder = new_folder 
                config_changed = True

            if new_scale_val != self.current_ui_scale:
                config["ui_scale"] = new_scale_val
                self.ui_scale_changed = True
                config_changed = True
                
                QMessageBox.information(
                    self, 
                    "Restart Required", 
                    "You have changed the UI Scale.\n\nPlease restart Media Nest for the new scaling to take effect!"
                )
                
            new_perf_val = self.perf_map[self.combo_perf.currentText()]
            if new_perf_val != self.current_perf_mode:
                config["performance_mode"] = new_perf_val
                self.current_perf_mode = new_perf_val
                config_changed = True
                
            if new_strictness != config.get("dedupe_strictness", 0):
                config["dedupe_strictness"] = new_strictness
                config_changed = True

            if new_strictness != config.get("dedupe_strictness", 0):
                config["dedupe_strictness"] = new_strictness
                config_changed = True
                
            if config_changed:
                with open(self.config_path, "w") as f: 
                    json.dump(config, f, indent=4)
                    
        except Exception as e:
            error_msg = f"Failed to save settings to:\n{self.config_path}\n\nError: {e}"
            QMessageBox.critical(self, "Save Error", error_msg)
            print(traceback.format_exc())
            return
            
        self.accept()

    def stop_all_media(self):
        """Scans the entire dialog for running media players and explicitly kills them."""
        
        players = self.findChildren(QMediaPlayer)
        for player in players:
            player.stop()
            player.setSource(QUrl())

    def flush_undo_trash(self):
        if not hasattr(self, 'undo_trash_dir') or not self.undo_trash_dir:
            return
            
        if os.path.exists(self.undo_trash_dir):
            for root, dirs, files in os.walk(self.undo_trash_dir):
                for f in files:
                    try:
                        send2trash(os.path.join(root, f))
                    except Exception:
                        pass

    def closeEvent(self, event):
        self.stop_all_media()
        self.flush_undo_trash()
        super().closeEvent(event)

    def reject(self):
        self.stop_all_media()
        self.flush_undo_trash()
        super().reject()

    def accept(self):
        self.stop_all_media()
        self.flush_undo_trash()
        super().accept()