import os
import json
import sqlite3
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QGroupBox, QFileDialog, 
                             QMessageBox, QTabWidget, QWidget, QComboBox, 
                             QScrollArea, QProgressBar, QCheckBox, QSlider, QFrame, QApplication)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QPixmap, QImageReader, QImage

from send2trash import send2trash  
from Src.Logic.deduplication import DeduplicationWorker
from Src.Logic.video_dedup import VideoDedupTab
from Src.Logic.tags import TagManagerTab
# ==========================================
# THUMBNAIL WORKER
# ==========================================
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
                reader.setScaledSize(orig_size.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio))
                img = reader.read()
                if not img.isNull():
                    self.thumb_ready.emit(path, img, res_text, size_mb)

# ==========================================
# 🔹 UPGRADED: FOCUSABLE IMAGE CLASS
# ==========================================
class FocusableClickableLabel(QLabel):
    clicked = pyqtSignal(str) 
    focused = pyqtSignal(str, QWidget) # Emits its path and itself when focused via keyboard
    
    def __init__(self, file_path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_path = file_path
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus) # 👈 Allows Tab and Arrow Key focus!

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.file_path)
            self.setFocus() # Focus the widget if clicked manually

    def focusInEvent(self, event):
        super().focusInEvent(event)
        # Draw a beautiful blue highlight when selected via keyboard
        self.setStyleSheet("background-color: #1e1e1e; border: 2px solid #0e639c; border-radius: 6px;")
        self.focused.emit(self.file_path, self)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        # Restore standard border when focus is lost
        self.setStyleSheet("background-color: #1e1e1e; border: 1px solid #454545; border-radius: 6px;")

# ==========================================
# MAIN DIALOG
# ==========================================
class SettingsDialog(QDialog):
    def __init__(self, config_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Media Nest Settings")
        self.setMinimumWidth(1100) 
        self.setMinimumHeight(700)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        
        # 🔹 DYNAMIC PORTABLE CONFIG FIX 🔹
        import sys
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.abspath(".") 
            
        self.config_path = os.path.join(base_dir, "config.json")
        self.current_db_folder = ""
        self.current_ui_scale = "1.0" 
        
        self.db_folder_changed = False
        self.ui_scale_changed = False
        self.dedupe_worker = None
        self.thumb_worker = None
        self.current_duplicate_groups = [] 
        self.current_preview_path = "" 
        self.auto_delete_mode = "safe" 
        
        self.thumb_labels_map = {} 
        self.nav_groups = [] # 👈 NEW: 2D Grid map for Arrow Key Navigation

        self.scale_map = {
            "50%": "0.5", "70%": "0.7", "90%": "0.9", "100% (Default)": "1.0",
            "125%": "1.25", "150%": "1.5", "175%": "1.75", "200%": "2.0"
        }
        self.reverse_scale_map = {v: k for k, v in self.scale_map.items()}

        self.load_config()
        self.setup_ui()

    def load_config(self):
        from PyQt6.QtCore import QSettings
        
        self.current_strictness = 0 
        
        # 1. 🔹 NEW: Always grab the official database folder from the OS Registry first!
        settings = QSettings("MediaNest", "AppConfig")
        self.current_db_folder = settings.value("db_folder_path", "", type=str)

        # 2. Load the rest of the visual settings from the JSON file
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    config = json.load(f)
                    
                    # Fallback: Only use the JSON db_folder if QSettings was somehow empty
                    if not self.current_db_folder:
                        self.current_db_folder = config.get("db_folder", "")
                        
                    self.current_ui_scale = config.get("ui_scale", "1.0")
                    self.current_strictness = config.get("dedupe_strictness", 0) 
            except Exception:
                pass

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tab_database = QWidget()
        self.tab_interface = QWidget()
        self.tab_dedupe = QWidget() 
        
        # 🔹 LAZY LOAD: Create empty placeholders instead of running heavy UI functions instantly
        self.tab_tag_manager = None
        self.tab_tag_placeholder = QWidget()
        
        self.tab_video_dedup = None
        self.tab_video_placeholder = QWidget()
        
        self.tabs.addTab(self.tab_database, "🗄️ Database")
        self.tabs.addTab(self.tab_interface, "🎨 Interface")
        self.tabs.addTab(self.tab_tag_placeholder, "🏷️ Tag Manager") 
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.tabs.addTab(self.tab_dedupe, "👯 Image Dedup")
        self.tabs.addTab(self.tab_video_placeholder, "🎥 Video Dedup")

        # --- DATABASE TAB ---
        db_layout = QVBoxLayout(self.tab_database)
        db_group = QGroupBox("Database Setup")
        db_inner_layout = QVBoxLayout()
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
        db_layout.addStretch()

        # --- INTERFACE TAB ---
        ui_layout = QVBoxLayout(self.tab_interface)
        ui_group = QGroupBox("Visual Settings")
        ui_inner_layout = QVBoxLayout()
        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("Window UI Scale (Requires Restart):"))
        self.combo_scale = QComboBox()
        self.combo_scale.addItems(list(self.scale_map.keys()))
        self.combo_scale.setCurrentText(self.reverse_scale_map.get(self.current_ui_scale, "100% (Default)"))
        scale_row.addWidget(self.combo_scale)
        scale_row.addStretch() 
        ui_inner_layout.addLayout(scale_row)
        ui_group.setLayout(ui_inner_layout)
        ui_layout.addWidget(ui_group)
        ui_layout.addStretch()

        # --- DEDUPLICATION DASHBOARD ---
        dedupe_layout = QVBoxLayout(self.tab_dedupe)
        dedupe_layout.setContentsMargins(10, 15, 10, 10)
        dedupe_layout.setSpacing(15)

        command_panel = QFrame()
        command_panel.setObjectName("CommandPanel")
        command_layout = QVBoxLayout(command_panel)
        command_layout.setContentsMargins(15, 15, 15, 15)

        action_row = QHBoxLayout()
        self.btn_scan_dupes = QPushButton("🔍 Scan Library")
        self.btn_scan_dupes.setFixedSize(140, 36)
        self.btn_scan_dupes.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan_dupes.clicked.connect(lambda: self.start_dedupe_scan(is_auto_rescan=False)) 
        
        self.btn_auto_delete = QPushButton("✨ Auto-Delete Low Res")
        self.btn_auto_delete.setFixedSize(210, 36)
        self.btn_auto_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto_delete.setEnabled(False)
        self.btn_auto_delete.clicked.connect(self.auto_delete_low_res)

        self.dedupe_search_bar = QLineEdit()
        self.dedupe_search_bar.setFixedHeight(36)
        self.dedupe_search_bar.setPlaceholderText("🔍 Filter duplicates by tags...")
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
        status_row.addWidget(self.lbl_dedupe_status)
        status_row.addStretch()

        command_layout.addLayout(status_row)
        dedupe_layout.addWidget(command_panel)

        self.pb_dedupe = QProgressBar()
        self.pb_dedupe.setFixedHeight(8)
        self.pb_dedupe.setTextVisible(False)
        self.pb_dedupe.setVisible(False)
        dedupe_layout.addWidget(self.pb_dedupe)

        # --- SPLIT VIEW ---
        content_split_layout = QHBoxLayout()

        self.dedupe_scroll = QScrollArea()
        self.dedupe_scroll.setWidgetResizable(True)
        self.dedupe_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.dedupe_scroll.setStyleSheet("QScrollArea { background-color: #1e1e1e; }")
        
        self.dedupe_content = QWidget()
        self.dedupe_content.setStyleSheet("QWidget { background-color: #1e1e1e; }")
        self.dedupe_content_layout = QVBoxLayout(self.dedupe_content)
        self.dedupe_content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.dedupe_content_layout.setSpacing(15) 
        
        self.dedupe_scroll.setWidget(self.dedupe_content)
        self.dedupe_scroll.verticalScrollBar().valueChanged.connect(self.on_dedupe_scroll)
        content_split_layout.addWidget(self.dedupe_scroll, stretch=6) 

        # --- THE NEW SCROLLABLE STACKED PREVIEW PANEL ---
        self.preview_panel = QFrame()
        self.preview_panel.setObjectName("PreviewPanel")
        self.preview_panel.setStyleSheet("#PreviewPanel { background-color: #252526; border-radius: 8px; border: 1px solid #3e3e42; }")
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        lbl_preview_title = QLabel("🔍 Group Comparison")
        lbl_preview_title.setStyleSheet("font-weight: bold; font-size: 15px; color: #ffffff;")
        preview_layout.addWidget(lbl_preview_title)

        # 1. Create a scroll area so we can handle 3+ images
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        # Hide the scrollbar background to make it look clean
        self.preview_scroll.setStyleSheet("""
            QScrollArea { background-color: transparent; border: none; }
            QScrollBar:vertical { background: #1e1e1e; width: 12px; }
            QScrollBar::handle:vertical { background: #424242; border-radius: 6px; }
            QScrollBar::handle:vertical:hover { background: #4f4f4f; }
        """)

        # 2. Container for the dynamic images
        self.preview_container = QWidget()
        self.preview_container.setStyleSheet("background-color: transparent;")
        
        # We use a Vertical Layout (QVBoxLayout) to stack them top-to-bottom
        self.preview_container_layout = QVBoxLayout(self.preview_container)
        self.preview_container_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.preview_container_layout.setSpacing(25) # Add nice padding between each image

        self.lbl_preview_placeholder = QLabel("Click an image to compare the group")
        self.lbl_preview_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview_placeholder.setStyleSheet("color: #666666; font-size: 14px;")
        self.preview_container_layout.addWidget(self.lbl_preview_placeholder)

        self.preview_scroll.setWidget(self.preview_container)
        preview_layout.addWidget(self.preview_scroll)

        content_split_layout.addWidget(self.preview_panel, stretch=4)
        dedupe_layout.addLayout(content_split_layout)
        main_layout.addWidget(self.tabs)

        # --- BOTTOM ACTION BUTTONS ---
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

    # ==========================================
    # 🔹 NEW: KEYBOARD NAVIGATION INTERCEPTOR
    # ==========================================
    def keyPressEvent(self, event):
        """Intercepts Arrow Keys to navigate the duplicate grid instantly without lag."""
        # Only hijack arrow keys if we are on the Deduplication tab and have a widget focused
        if self.tabs.currentIndex() != 2 or not self.nav_groups:
            super().keyPressEvent(event)
            return

        focus_widget = QApplication.focusWidget()
        if not isinstance(focus_widget, FocusableClickableLabel):
            super().keyPressEvent(event)
            return

        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Down):
            
            # 1. Fast Lookup: Find exactly where we currently are without building a new grid
            current_g, current_i = -1, -1
            for g_idx, group in enumerate(self.nav_groups):
                if focus_widget in group:
                    current_g = g_idx
                    current_i = group.index(focus_widget)
                    break

            if current_g == -1:
                super().keyPressEvent(event)
                return

            # Helper function: Instantly try to focus the target. Safely ignores deleted images.
            def try_focus(g, i):
                try:
                    if 0 <= g < len(self.nav_groups) and 0 <= i < len(self.nav_groups[g]):
                        w = self.nav_groups[g][i]
                        if w.isVisible():
                            w.setFocus()
                            return True
                except RuntimeError:
                    pass # Object was moved to Recycle Bin and deleted from C++ memory
                return False

            # 2. Process Movement (0(1) complexity = Zero Lag!)
            if event.key() == Qt.Key.Key_Right:
                if not try_focus(current_g, current_i + 1):
                    try_focus(current_g + 1, 0) # Wrap to next group
                event.accept()
                
            elif event.key() == Qt.Key.Key_Left:
                if not try_focus(current_g, current_i - 1):
                    if current_g > 0:
                        try_focus(current_g - 1, len(self.nav_groups[current_g - 1]) - 1) # Wrap to previous
                event.accept()
                
            elif event.key() == Qt.Key.Key_Down:
                # Jump down to the next valid group
                for next_g in range(current_g + 1, len(self.nav_groups)):
                    target_i = min(current_i, len(self.nav_groups[next_g]) - 1)
                    if try_focus(next_g, target_i):
                        break
                event.accept()
                
            elif event.key() == Qt.Key.Key_Up:
                # Jump up to the previous valid group
                for prev_g in range(current_g - 1, -1, -1):
                    target_i = min(current_i, len(self.nav_groups[prev_g]) - 1)
                    if try_focus(prev_g, target_i):
                        break
                event.accept()
        else:
            # Let default keys (like Tab/Shift+Tab) behave normally
            super().keyPressEvent(event)

    def on_dedupe_scroll(self, scroll_value):
        """Detects which duplicate group is currently visible and updates the preview."""
        if not self.current_duplicate_groups:
            return

        for idx in range(self.dedupe_content_layout.count()):
            widget = self.dedupe_content_layout.itemAt(idx).widget()
            
            if widget and widget.isVisible():
                # If the bottom 60% of the group card is still visible in the viewport
                if widget.y() + (widget.height() * 0.4) > scroll_value:
                    
                    group_idx = widget.property("group_index")
                    first_img = widget.property("first_image")
                    
                    # Only update if we scrolled into a NEW group
                    if first_img and getattr(self, 'active_preview_group', -1) != group_idx:
                        self.active_preview_group = group_idx
                        self.show_preview(first_img)
                    break

    # ==========================================
    # PREVIEW ENGINE
    # ==========================================
    def on_thumbnail_focused(self, file_path, widget):
        """Triggered automatically when the keyboard focus lands on an image."""
        self.show_preview(file_path)
        # Ensure the scrollbar smoothly chases the active widget!
        self.dedupe_scroll.ensureWidgetVisible(widget, 50, 100)

    def show_preview(self, file_path):
        if not os.path.exists(file_path): 
            return
            
        self.current_preview_path = file_path
        
        # 1. Find the duplicate group this image belongs to
        target_group = None
        for group_data in self.current_duplicate_groups:
            items = group_data[0]
            if any(item['path'] == file_path for item in items):
                target_group = items
                break
        
        if not target_group:
            target_group = [{'path': file_path}] # Fallback if not found
            
        # 2. Clear existing preview container
        for i in reversed(range(self.preview_container_layout.count())):
            w = self.preview_container_layout.itemAt(i).widget()
            if w: w.setParent(None)

        # ==========================================
        # 🔹 DYNAMIC 2-FIT SCALING ENGINE
        # ==========================================
        # Get the exact pixel height available on the user's monitor right now
        viewport_height = self.preview_scroll.viewport().height()
        viewport_width = self.preview_scroll.viewport().width()
        
        # Divide the height by 2, and subtract 65 pixels to leave room for the text labels and borders.
        # This mathematically guarantees the first 2 images will fit without triggering a scrollbar!
        target_h = int((viewport_height / 2) - 65)
        target_w = int(viewport_width - 40)
        
        # Fallback minimums just in case the window gets resized extremely small
        target_h = max(target_h, 150)
        target_w = max(target_w, 150)
            
        # 3. Build dynamically stacked previews
        for index, item in enumerate(target_group):
            path = item['path']
            if not os.path.exists(path): continue
            
            item_widget = QWidget()
            item_layout = QVBoxLayout(item_widget)
            item_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            
            lbl_img = QLabel()
            lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            reader = QImageReader(path)
            orig_size = reader.size()
            if orig_size.isValid():
                # Force the image to scale down to our mathematically perfect target size!
                reader.setScaledSize(orig_size.scaled(target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio))
                img = reader.read()
                if not img.isNull():
                    lbl_img.setPixmap(QPixmap.fromImage(img))
            
            lbl_info = QLabel()
            lbl_info.setWordWrap(True)
            lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_info.setStyleSheet("color: #cccccc; font-size: 13px; margin-top: 5px; line-height: 1.5;")
            
            res_text = f"{orig_size.width()}x{orig_size.height()}" if orig_size.isValid() else "Unknown"
            size_mb = os.path.getsize(path) / (1024 * 1024)
            filename = os.path.basename(path)
            
            # Highlight the specific image you clicked on!
            is_selected = (path == file_path)
            text_color = "#00a2ff" if is_selected else "#ffffff"
            border_color = "#00a2ff" if is_selected else "#454545"
            
            lbl_img.setStyleSheet(f"background-color: #1e1e1e; border: 2px solid {border_color}; border-radius: 6px; padding: 5px;")
            
            info_html = (
                f"<b style='color:{text_color}; font-size:15px;'>Image {index + 1}: {filename}</b><br>"
                f"<b>📐 Res:</b> {res_text} &nbsp;&nbsp;|&nbsp;&nbsp; <b>💾 Size:</b> {size_mb:.2f} MB"
            )
            lbl_info.setText(info_html)
            
            item_layout.addWidget(lbl_img)
            item_layout.addWidget(lbl_info)
            
            self.preview_container_layout.addWidget(item_widget)

    def on_tab_changed(self, index):
        tab_name = self.tabs.tabText(index)
        
        # 1. Check if the user clicked an advanced tab
        if tab_name in ["🏷️ Tag Manager", "👯 Image Dedup", "🎥 Video Dedup"]:
            from PyQt6.QtCore import QSettings
            settings = QSettings("MediaNest", "AppConfig")
            
            # 2. If they haven't set up a database, show the popup!
            if not settings.value("db_folder_path"):
                from Src.Dialogs.setup_dialog import FirstTimeSetupDialog
                setup_window = FirstTimeSetupDialog(self)
                
                if setup_window.exec() == QDialog.DialogCode.Accepted:
                    # They finished setup! Reload the config to get the new path
                    self.load_config()
                    self.db_path_input.setText(self.current_db_folder)
                else:
                    # They cancelled the setup. Kick them back to the Interface tab!
                    self.tabs.setCurrentIndex(1) 
                    return

        # 3. 🔹 LAZY LOADING LOGIC 🔹
        if tab_name == "🏷️ Tag Manager":
            # If it hasn't been built yet, build it now!
            if self.tab_tag_manager is None:
                self.tabs.setTabText(index, "⏳ Loading...")
                QApplication.processEvents() # Force UI to show loading text
                
                self.tab_tag_manager = TagManagerTab(self)
                self.tabs.removeTab(index)
                self.tabs.insertTab(index, self.tab_tag_manager, "🏷️ Tag Manager")
                self.tabs.setCurrentIndex(index)
            
            # 🔹 ANTI-FREEZE: Delay the database refresh by 20ms so the UI switches tabs instantly!
            QTimer.singleShot(20, self.tab_tag_manager.refresh_global_tags)
            QTimer.singleShot(20, self.tab_tag_manager.refresh_tagless_inbox)

        elif tab_name == "🎥 Video Dedup":
            if self.tab_video_dedup is None:
                self.tabs.setTabText(index, "⏳ Loading...")
                QApplication.processEvents()
                
                self.tab_video_dedup = VideoDedupTab(self)
                self.tabs.removeTab(index)
                self.tabs.insertTab(index, self.tab_video_dedup, "🎥 Video Dedup")
                self.tabs.setCurrentIndex(index)

    def clear_preview(self):
        self.current_preview_path = ""
        
        # Delete all dynamic images in the layout
        for i in reversed(range(self.preview_container_layout.count())):
            w = self.preview_container_layout.itemAt(i).widget()
            if w: w.setParent(None)
            
        # Put the placeholder text back
        self.lbl_preview_placeholder = QLabel("Click an image to compare the group")
        self.lbl_preview_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview_placeholder.setStyleSheet("color: #666666; font-size: 14px;")
        self.preview_container_layout.addWidget(self.lbl_preview_placeholder)


    # ==========================================
    # DEDUPLICATION WORKER LOGIC
    # ==========================================
    def start_dedupe_scan(self, is_auto_rescan=False):
        if not is_auto_rescan: self.auto_delete_mode = "safe"

        if not self.current_db_folder: 
            QMessageBox.warning(self, "No Database Folder", "Please select your 'Library Folder' in the Database tab first, then hit Save Settings!")
            return

        db_file = os.path.join(self.current_db_folder, "library.db")
        if not os.path.exists(db_file): 
            QMessageBox.critical(self, "Database Missing", f"Could not find library.db at:\n\n{db_file}\n\nPlease check your folder path in the Database tab.")
            return

        self.btn_scan_dupes.setEnabled(False)
        self.btn_scan_dupes.setText("⏳ Scanning...")
        self.pb_dedupe.setVisible(True)
        self.pb_dedupe.setValue(0)
        
        self.btn_auto_delete.setEnabled(False)
        self.dedupe_search_bar.setEnabled(False)
        self.clear_preview() 
        self.thumb_labels_map.clear()
        self.nav_groups.clear() # 👈 Reset the navigation map
        
        self.render_queue = []
        for i in reversed(range(self.dedupe_content_layout.count())):
            w = self.dedupe_content_layout.itemAt(i).widget()
            if w: w.setParent(None)

        self.dedupe_worker = DeduplicationWorker(db_file, self.slider_strictness.value())
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
        self.btn_scan_dupes.setText("🔍 Scan Library")
        self.pb_dedupe.setVisible(False)

    def render_duplicates_ui(self, duplicate_groups):
        self.current_duplicate_groups = duplicate_groups 

        if not duplicate_groups:
            self.lbl_dedupe_status.setText("✅ Library is clean! No duplicates found.")
            return

        self.btn_auto_delete.setEnabled(True)
        self.dedupe_search_bar.setEnabled(True)

        if self.auto_delete_mode == "safe": self.btn_auto_delete.setText("✨ Auto-Delete Low Res")
        else: self.btn_auto_delete.setText("✨ Auto-Delete Low MB (Same Res)")

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
            widgets['thumb'].setPixmap(QPixmap.fromImage(qimage))
            widgets['info'].setText(f"📐 {res_text}  |  💾 {size_mb} MB")

    def render_next_batch(self):
        if not self.render_queue:
            self.lbl_dedupe_status.setText(f"Done! Displaying {self.total_render_items} duplicate groups.")
            self.pb_dedupe.setVisible(False)
            
            # --- NEW: Auto-load the first visible group! ---
            self.on_dedupe_scroll(self.dedupe_scroll.verticalScrollBar().value())
            return

        i, group_data = self.render_queue.pop(0)
        # ... (keep the rest of the method exactly the same)
        group_items, group_tags, avg_conf = group_data 

        rendered_count = self.total_render_items - len(self.render_queue)
        self.pb_dedupe.setValue(rendered_count)
        self.lbl_dedupe_status.setText(f"Loading images... {rendered_count} / {self.total_render_items}")

        group_card = QFrame()
        group_card.setObjectName("GroupCard")
        group_card.setProperty("search_tags", group_tags)
        group_card.setProperty("group_index", i) 
        group_card.setProperty("first_image", group_items[0]['path'])
        group_card.setStyleSheet("#GroupCard { background-color: #2d2d30; border-radius: 8px; border: 1px solid #3e3e42; }")
        
        card_main_layout = QVBoxLayout(group_card)
        card_main_layout.setContentsMargins(15, 15, 15, 15)

        header_layout = QHBoxLayout()
        lbl_title = QLabel(f"📄 Duplicate Group #{i+1}")
        lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
        lbl_conf = QLabel(f"Confidence: {avg_conf}%")
        conf_color = "#3fb950" if avg_conf > 90 else "#d29922"
        lbl_conf.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {conf_color}; background-color: rgba(0,0,0,0.2); padding: 4px 8px; border-radius: 4px;")
        
        btn_ignore = QPushButton("✅ Mark as 'Not Duplicates'")
        btn_ignore.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ignore.setStyleSheet("QPushButton { background-color: transparent; border: 1px solid #3fb950; color: #3fb950; padding: 4px 10px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: rgba(63, 185, 80, 0.1); }")
        
        # --- NEW: Delete All Button ---
        btn_delete_all = QPushButton("🗑️ Delete All")
        btn_delete_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_delete_all.setStyleSheet("QPushButton { background-color: transparent; border: 1px solid #a31515; color: #a31515; padding: 4px 10px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: rgba(163, 21, 21, 0.1); }")
        
        header_layout.addWidget(lbl_title)
        header_layout.addWidget(lbl_conf)
        header_layout.addStretch()
        header_layout.addWidget(btn_delete_all) # Add the new button here
        header_layout.addWidget(btn_ignore)
        card_main_layout.addLayout(header_layout)
        
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #3e3e42;")
        card_main_layout.addWidget(line)

        group_images_layout = QHBoxLayout()
        group_images_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        has_checkboxes = len(group_items) >= 3
        checkbox_refs = [] 
        
        # 🔹 NEW: Array to collect the images for this specific row
        nav_group_row = [] 
        
        for item in group_items:
            file_path = item['path']
            
            item_widget = QWidget()
            item_widget.setFixedWidth(160) 
            item_layout = QVBoxLayout(item_widget)
            item_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            item_layout.setContentsMargins(5, 5, 5, 5)
            
            thumb_layout = QVBoxLayout()
            
            # --- USING THE NEW FOCUSABLE CLASS ---
            lbl_thumb = FocusableClickableLabel(file_path)
            lbl_thumb.clicked.connect(self.show_preview) 
            lbl_thumb.focused.connect(self.on_thumbnail_focused) # Trigger preview when tabbed to!
            # -------------------------------------
            
            lbl_thumb.setFixedSize(150, 150) 
            lbl_thumb.setStyleSheet("background-color: #1e1e1e; border: 1px solid #454545; border-radius: 6px;")
            lbl_thumb.setText("Loading...")
            lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            nav_group_row.append(lbl_thumb)
            
            thumb_layout.addWidget(lbl_thumb)
            if has_checkboxes:
                cb = QCheckBox("Select Exception")
                cb.setCursor(Qt.CursorShape.PointingHandCursor)
                cb.setProperty("hash_val", item['hash']) 
                checkbox_refs.append(cb)
                thumb_layout.addWidget(cb)

            lbl_name = QLabel(os.path.basename(file_path))
            lbl_name.setWordWrap(True)
            lbl_name.setStyleSheet("font-weight: bold; margin-top: 4px; font-size: 12px; color: #e0e0e0;")
            
            lbl_info = QLabel("Loading info...")
            lbl_info.setStyleSheet("color: #858585; font-size: 11px;")

            self.thumb_labels_map[file_path] = {'thumb': lbl_thumb, 'info': lbl_info}

            btn_del = QPushButton("🗑️ Recycle Bin")
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setStyleSheet("QPushButton { background-color: #a31515; color: white; padding: 6px; margin-top: 4px; border-radius: 4px; } QPushButton:hover { background-color: #d13438; }")
            btn_del.clicked.connect(lambda checked, p=file_path, w=item_widget: self.delete_duplicate(p, w))

            item_layout.addLayout(thumb_layout)
            item_layout.addWidget(lbl_name)
            item_layout.addWidget(lbl_info)
            item_layout.addWidget(btn_del)
            group_images_layout.addWidget(item_widget)

        # 🔹 NEW: Add this group's images to the global navigation map
        if nav_group_row:
            self.nav_groups.append(nav_group_row)

        card_main_layout.addLayout(group_images_layout)
        btn_ignore.clicked.connect(lambda checked, gc=group_card, gd=group_data, cbs=checkbox_refs: self.mark_not_duplicates(gc, gd, cbs))
        btn_delete_all.clicked.connect(lambda checked, gc=group_card, gd=group_data: self.delete_all_duplicates(gc, gd))
        self.dedupe_content_layout.addWidget(group_card)
        QTimer.singleShot(5, self.render_next_batch)

    # ==========================================
    # EXCEPTION MANAGER
    # ==========================================
    # ==========================================
    # EXCEPTION MANAGER
    # ==========================================
    def mark_not_duplicates(self, group_card, group_data, checkboxes):
        group_items = group_data[0] # Unpack the items for the database logic
        
        db_file = os.path.join(self.current_db_folder, "library.db")
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        all_hashes = [item['hash'] for item in group_items]
        pairs_to_ignore = []

        if not checkboxes:
            pairs_to_ignore.append(tuple(sorted((all_hashes[0], all_hashes[1]))))
        else:
            selected_hashes = []
            for cb in checkboxes:
                try:
                    if cb.isChecked():
                        selected_hashes.append(cb.property("hash_val"))
                except RuntimeError:
                    continue 
            
            if not selected_hashes: 
                QMessageBox.warning(self, "Selection Required", "Please check the box next to the image(s) that are not duplicates.")
                return conn.close()
                
            for selected in selected_hashes:
                for other in all_hashes:
                    if selected != other:
                        pairs_to_ignore.append(tuple(sorted((selected, other))))
        
        for h1, h2 in set(pairs_to_ignore):
            cursor.execute("INSERT OR IGNORE INTO IgnoredPairs (hash1, hash2) VALUES (?, ?)", (h1, h2))
            
        conn.commit()
        conn.close()
        
        # --- 🔹 NEW: Purge the group from active memory! ---
        if group_data in self.current_duplicate_groups:
            self.current_duplicate_groups.remove(group_data)
        # ---------------------------------------------------
        
        group_card.setParent(None)
        group_card.deleteLater()

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

    # ==========================================
    # TWO-PHASE AUTO DELETE ENGINE
    # ==========================================
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
                self.btn_auto_delete.setText("✨ Auto-Delete Low MB (Same Res)")
                QMessageBox.information(self, "Phase 1 Complete", "All strictly low-resolution duplicates have been cleaned!\n\nThe button has now updated to Phase 2. Click it again to clean up duplicates that share the exact same resolution by keeping the largest/best file.")
            else:
                QMessageBox.information(self, "Fully Clean", "No remaining duplicates found to auto-delete.")
            return

        mode_text = "strictly lower resolution" if self.auto_delete_mode == "safe" else "lower quality (identical resolutions)"
        reply = QMessageBox.question(self, "Confirm Send to Recycle Bin", f"Found {len(files_to_delete)} {mode_text} duplicates.\n\nAre you sure you want to move them to the Recycle Bin?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
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
            QMessageBox.information(self, "Success", f"Moved {self.deleted_count} files to the Recycle Bin!")
            
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

    def delete_duplicate(self, file_path, widget_to_remove):
        reply = QMessageBox.question(self, "Confirm", f"Move this file to the Recycle Bin?\n{os.path.basename(file_path)}", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if os.path.exists(file_path): send2trash(file_path)
                db_file = os.path.join(self.current_db_folder, "library.db")
                conn = sqlite3.connect(db_file)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM Images WHERE file_path = ?", (file_path,))
                conn.commit()
                conn.close()
                
                if self.current_preview_path == file_path: self.clear_preview()
                
                widget_to_remove.setParent(None)
                widget_to_remove.deleteLater()
            except Exception:
                pass

    def delete_all_duplicates(self, group_card, group_data):
        group_items = group_data[0]
        
        reply = QMessageBox.question(
            self, 
            "Confirm Delete All", 
            f"Are you sure you want to move ALL {len(group_items)} images in this group to the Recycle Bin?", 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            db_file = os.path.join(self.current_db_folder, "library.db")
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            paths_to_delete = [item['path'] for item in group_items]
            
            for path in paths_to_delete:
                try:
                    if os.path.exists(path):
                        send2trash(path)
                    cursor.execute("DELETE FROM Images WHERE file_path = ?", (path,))
                except Exception as e:
                    print(f"Failed to delete {path}: {e}")
                    
            conn.commit()
            conn.close()
            
            # Check if one of the deleted images is currently loaded in the preview panel
            if self.current_preview_path in paths_to_delete:
                self.clear_preview()
                
            # Remove from background memory
            if group_data in self.current_duplicate_groups:
                self.current_duplicate_groups.remove(group_data)
                
            # Remove the entire group card from the UI
            group_card.setParent(None)
            group_card.deleteLater()

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Database Folder", self.current_db_folder)
        if folder: self.db_path_input.setText(os.path.normpath(folder))

    def save_settings(self):
        from PyQt6.QtCore import QSettings
        import traceback
        
        new_folder = self.db_path_input.text().strip()
        new_scale_val = self.scale_map[self.combo_scale.currentText()]
        new_strictness = self.slider_strictness.value() 
        config_changed = False
        
        # Update the Global Windows Registry
        settings = QSettings("MediaNest", "AppConfig")
        if new_folder:
            settings.setValue("db_folder_path", new_folder)
        else:
            settings.remove("db_folder_path")

        try:
            config = {}
            # 🔹 BUG FIX: Safely handle empty or corrupted config files
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path, "r") as f: 
                        config = json.load(f)
                except json.JSONDecodeError:
                    config = {} # If the file is blank or broken, just start fresh!
            
            if new_folder != self.current_db_folder:
                config["db_folder"] = new_folder
                self.current_db_folder = new_folder 
                config_changed = True

            if new_scale_val != self.current_ui_scale:
                config["ui_scale"] = new_scale_val
                self.ui_scale_changed = True
                config_changed = True
                
                # Warn the user to restart!
                QMessageBox.information(
                    self, 
                    "Restart Required", 
                    "You have changed the UI Scale.\n\nPlease restart Media Nest for the new scaling to take effect!"
                )
                
            if new_strictness != config.get("dedupe_strictness", 0):
                config["dedupe_strictness"] = new_strictness
                config_changed = True
                
            if config_changed:
                with open(self.config_path, "w") as f: 
                    json.dump(config, f, indent=4)
                    
        except Exception as e:
            # 🔹 BUG FIX: If it fails, actually show an error popup instead of freezing!
            error_msg = f"Failed to save settings to:\n{self.config_path}\n\nError: {e}"
            QMessageBox.critical(self, "Save Error", error_msg)
            print(traceback.format_exc())
            return
            
        self.accept()

    def stop_all_media(self):
        """Scans the entire dialog for running media players and explicitly kills them."""
        from PyQt6.QtMultimedia import QMediaPlayer
        from PyQt6.QtCore import QUrl
        
        # Find every single QMediaPlayer inside this dialog (including the one in the Dedup Tab)
        players = self.findChildren(QMediaPlayer)
        for player in players:
            player.stop()
            player.setSource(QUrl()) # completely releases the file lock!

    # Override the 'X' button close event
    def closeEvent(self, event):
        self.stop_all_media()
        super().closeEvent(event)

    # Override the 'Cancel' or 'Escape' key event
    def reject(self):
        self.stop_all_media()
        super().reject()

    # Override the 'Save' or 'OK' button event
    def accept(self):
        self.stop_all_media()
        super().accept()