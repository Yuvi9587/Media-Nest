import os
import sys
import sqlite3
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
                             QLineEdit, QPushButton, QListWidget, QListWidgetItem,
                             QScrollArea, QFrame, QFileDialog, QMessageBox, QSplitter, QProgressBar,
                             QStyledItemDelegate)
from PyQt6.QtCore import Qt, QSize, QTimer, QPropertyAnimation, QRect
from PyQt6.QtGui import QIcon, QPixmap, QImageReader, QPainter, QColor
import re
from Src.Logic.paths import resource_path

def natural_key(text):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", text)]

class PageNumberDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        link_path = resource_path(os.path.join("assets", "uisvg", "link.svg"))
        self.link_icon = QIcon(link_path)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        page_num = index.row() + 1
        page_text = f"Pg {page_num}"
        painter.save()
        rect = option.rect
        painter.setPen(QColor("#888888"))
        painter.drawText(option.rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, page_text)
        
        is_attached = index.data(Qt.ItemDataRole.UserRole + 2)
        is_attached_to_prev = False
        if index.row() > 0:
            prev_index = index.model().index(index.row() - 1, 0)
            is_attached_to_prev = index.model().data(prev_index, Qt.ItemDataRole.UserRole + 2)
            
        icon_size = 20
        pixmap = self.link_icon.pixmap(icon_size, icon_size)
        icon_w, icon_h = pixmap.width(), pixmap.height()
        
        x = rect.right() - 50
        
        if is_attached:
            y = rect.bottom() - icon_h // 2 + 1
            painter.drawPixmap(x, y, pixmap, 0, 0, icon_w, icon_h // 2)
            
        if is_attached_to_prev:
            y = rect.top()
            painter.drawPixmap(x, y, pixmap, 0, icon_h // 2, icon_w, icon_h - icon_h // 2)
            
        painter.restore()

class SearchItemDelegate(QStyledItemDelegate):
    def __init__(self, pagination_tab, parent=None):
        super().__init__(parent)
        self.pagination_tab = pagination_tab

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        
        path = index.data(Qt.ItemDataRole.UserRole)
        if path in self.pagination_tab.selected_images:
            page_num = self.pagination_tab.selected_images.index(path) + 1
            
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            radius = 12
            margin = 8
            rect = option.rect
            center_x = rect.right() - radius - margin
            center_y = rect.top() + radius + margin
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#00a2ff"))
            painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)
            
            painter.setPen(QColor("white"))
            font = painter.font()
            font.setBold(True)
            font.setPointSize(10)
            painter.setFont(font)
            text_rect = QRect(center_x - radius, center_y - radius, radius * 2, radius * 2)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(page_num))
            
            painter.restore()
class Snackbar(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QLabel {
                background-color: #0e639c;
                color: white;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        self.hide()
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(300)
        
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide_snackbar)
        
    def show_message(self, message, duration=6000):
        self.setText(message)
        self.adjustSize()
        
        parent_rect = self.parentWidget().rect()
        start_rect = QRect(
            (parent_rect.width() - self.width()) // 2,
            parent_rect.height(),
            self.width(),
            self.height()
        )
        end_rect = QRect(
            (parent_rect.width() - self.width()) // 2,
            parent_rect.height() - self.height() - 20,
            self.width(),
            self.height()
        )
        
        self.setGeometry(start_rect)
        self.show()
        self.raise_()
        
        self.animation.setStartValue(start_rect)
        self.animation.setEndValue(end_rect)
        self.animation.start()
        
        self.timer.start(duration)
        
    def hide_snackbar(self):
        end_rect = QRect(
            self.geometry().x(),
            self.parentWidget().rect().height(),
            self.width(),
            self.height()
        )
        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(end_rect)
        self.animation.start()
        self.animation.finished.connect(self.hide)


class FolderItemWidget(QWidget):
    def __init__(self, title, image_paths, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-weight: bold; font-size: 14px; color: white;")
        lbl_title.setWordWrap(True)
        layout.addWidget(lbl_title)
        
        grid = QGridLayout()
        grid.setSpacing(5)
        self.image_labels = {}
        
        MAX_PREVIEW = 10
        col_count = 5
        
        for idx, path in enumerate(image_paths[:MAX_PREVIEW]):
            lbl = QLabel()
            lbl.setFixedSize(60, 80)
            lbl.setStyleSheet("background-color: #2a2a2a; border-radius: 4px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(lbl, idx // col_count, idx % col_count)
            self.image_labels[path] = lbl
            
        layout.addLayout(grid)


class PaginationTab(QWidget):
    def __init__(self, parent_dialog):
        super().__init__()
        self.parent_dialog = parent_dialog
        self.db_path = parent_dialog.current_db_folder
        if self.db_path:
            self.db_path = os.path.join(self.db_path, "library.db")
            
        self.selected_images = []
        self.is_grouped = True
        self.last_imported_leaf_folders = []
        
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(150)
        self.preview_timer.timeout.connect(self.load_preview_image)
        self.current_preview_path = None
        
        self.loaded_manga_id = None
        
        self.setup_ui()
        self.load_tags_for_completer()

    def load_tags_for_completer(self):
        try:
            from Src.Logic.tags import DbLookupCompleter
            from Src.Logic.app import NsTabExpander

            library_db = self.db_path or ""
            appdata_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "appdata")
            os.makedirs(appdata_dir, exist_ok=True)
            alltags_db = os.path.join(appdata_dir, "AllTags.db")

            self.tag_completer = DbLookupCompleter(self)
            self.tag_completer.set_db_paths(alltags_db, library_db)
            self.search_input.setCompleter(self.tag_completer)
            self.search_input.textEdited.connect(self.tag_completer.on_text_changed)
            self.tag_completer.activated.connect(self.on_completer_activated)

            self._search_expander = NsTabExpander(self.search_input, self)
            self.search_input.installEventFilter(self._search_expander)

            self.custom_tags_completer = DbLookupCompleter(self)
            self.custom_tags_completer.set_db_paths(alltags_db, library_db)
            if hasattr(self, 'tags_input'):
                self.tags_input.setCompleter(self.custom_tags_completer)
                self.tags_input.textEdited.connect(self.custom_tags_completer.on_text_changed)

                self._tags_expander = NsTabExpander(self.tags_input, self)
                self.tags_input.installEventFilter(self._tags_expander)
        except Exception as e:
            print(f"Completer error: {e}")

    def on_completer_activated(self, text):
        self.search_input.setText(text)
        self.perform_search()

    def setup_ui(self):
        from Src.Logic.app import SingleThumbnailThread
        self.thumb_thread = SingleThumbnailThread()
        self.thumb_thread.thumbnail_ready.connect(self.on_thumbnail_ready)
        self.thumb_thread.start()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 15, 10, 10)
        main_layout.setSpacing(10)

        top_bar = QHBoxLayout()
        self.btn_import = QPushButton("Import Folder")
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.setStyleSheet("QPushButton { font-size: 1em; background-color: #0e639c; color: white; border-radius: 4px; font-weight: bold; padding: 8px 15px; } QPushButton:hover { background-color: #1177bb; }")
        self.btn_import.clicked.connect(self.import_folder)
        top_bar.addWidget(self.btn_import)
        
        self.btn_load_existing = QPushButton("Load Existing")
        self.btn_load_existing.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_load_existing.setStyleSheet("QPushButton { font-size: 1em; background-color: #0e639c; color: white; border-radius: 4px; font-weight: bold; padding: 8px 15px; margin-left: 10px; } QPushButton:hover { background-color: #1177bb; }")
        self.btn_load_existing.clicked.connect(self.load_existing_manga)
        top_bar.addWidget(self.btn_load_existing)
        
        self.btn_clear = QPushButton("Clear / New")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setStyleSheet("QPushButton { font-size: 1em; background-color: #d13438; color: white; border-radius: 4px; font-weight: bold; padding: 8px 15px; margin-left: 10px; } QPushButton:hover { background-color: #e81123; }")
        self.btn_clear.clicked.connect(self.clear_manga_state)
        top_bar.addWidget(self.btn_clear)
        
        from PyQt6.QtGui import QIcon
        import sys
        base = getattr(sys, '_MEIPASS', os.path.abspath("."))
        self.btn_group_toggle = QPushButton()
        self.btn_group_toggle.setIcon(QIcon(os.path.join(base, "assets", "uisvg", "ungroup.svg")))
        self.btn_group_toggle.setToolTip("Ungroup Folders")
        self.btn_group_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_group_toggle.setStyleSheet("QPushButton { background-color: #3e3e42; border-radius: 4px; padding: 8px; margin-left: 10px; } QPushButton:hover { background-color: #505050; }")
        self.btn_group_toggle.clicked.connect(self.toggle_group)
        self.btn_group_toggle.hide()
        top_bar.addWidget(self.btn_group_toggle)
        
        top_bar.addStretch()
        main_layout.addLayout(top_bar)

        columns_splitter = QSplitter(Qt.Orientation.Horizontal)
        columns_splitter.setChildrenCollapsible(False)
        
        col1_frame = QFrame()
        col1_frame.setStyleSheet("QFrame { background-color: #252526; border-radius: 8px; border: 1px solid #3e3e42; }")
        col1_layout = QVBoxLayout(col1_frame)
        col1_layout.setContentsMargins(10, 10, 10, 10)
        
        lbl_search = QLabel("1. Search & Select")
        lbl_search.setStyleSheet("font-weight: bold; font-size: 1.1em; border: none;")
        col1_layout.addWidget(lbl_search)
        
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by tag...")
        self.search_input.returnPressed.connect(self.perform_search)
        search_row.addWidget(self.search_input)
        
        col1_layout.addLayout(search_row)
        
        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setFixedHeight(4)
        self.loading_bar.setStyleSheet("QProgressBar { border: none; background-color: transparent; } QProgressBar::chunk { background-color: #0e639c; border-radius: 2px; }")
        self.loading_bar.hide()
        col1_layout.addWidget(self.loading_bar)
        
        from PyQt6.QtWidgets import QListView, QAbstractItemView
        self.search_list = QListWidget()
        self.search_list.setViewMode(QListView.ViewMode.IconMode)
        self.search_list.setIconSize(QSize(180, 180))
        self.search_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.search_list.setSpacing(10)
        self.search_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.search_list.setStyleSheet("QListWidget { background-color: #1e1e1e; border: 1px solid #3e3e42; } QListWidget::item { padding: 5px; border-radius: 5px; } QListWidget::item:selected { background-color: #0e639c; }")
        self.search_list.itemSelectionChanged.connect(self.on_search_selection_changed)
        self.search_list.currentItemChanged.connect(self.on_org_item_selected)
        self.search_list.setItemDelegate(SearchItemDelegate(self, self.search_list))
        col1_layout.addWidget(self.search_list)
        columns_splitter.addWidget(col1_frame)
        
        col2_frame = QFrame()
        col2_frame.setStyleSheet("QFrame { background-color: #252526; border-radius: 8px; border: 1px solid #3e3e42; }")
        col2_layout = QVBoxLayout(col2_frame)
        col2_layout.setContentsMargins(10, 10, 10, 10)
        
        lbl_org = QLabel("2. Organize Pages")
        lbl_org.setStyleSheet("font-weight: bold; font-size: 1.1em; border: none;")
        col2_layout.addWidget(lbl_org)
        
        self.org_list = QListWidget()
        self.org_list.setStyleSheet("""
            QListWidget { background-color: #1e1e1e; border: 1px solid #3e3e42; outline: none; }
            QListWidget::item { border-bottom: 1px solid #333; padding: 8px; border-radius: 4px; margin: 2px; }
            QListWidget::item:hover { background-color: #2a2d2e; }
            QListWidget::item:selected { background-color: #04395e; border: 1px solid #0e639c; }
            QListWidget::drop-indicator { background: #00a2ff; height: 3px; border-radius: 1px; }
        """)
        self.org_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.org_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.org_list.setDropIndicatorShown(True)
        self.org_list.setItemDelegate(PageNumberDelegate(self.org_list))
        self.org_list.currentItemChanged.connect(self.on_org_item_selected)
        self.org_list.model().rowsMoved.connect(self._update_selected_images_order)
        self.org_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.org_list.customContextMenuRequested.connect(self.show_org_context_menu)
        
        org_controls_layout = QHBoxLayout()
        self.btn_up = QPushButton("Move Up")
        self.btn_down = QPushButton("Move Down")
        self.btn_remove = QPushButton("Remove")
        
        self.btn_up.clicked.connect(self.move_up)
        self.btn_down.clicked.connect(self.move_down)
        self.btn_remove.clicked.connect(self.remove_item)
        
        org_controls_layout.addWidget(self.btn_up)
        org_controls_layout.addWidget(self.btn_down)
        org_controls_layout.addWidget(self.btn_remove)
        
        col2_layout.addWidget(self.org_list)
        col2_layout.addLayout(org_controls_layout)
        columns_splitter.addWidget(col2_frame)

        col3_frame = QFrame()
        col3_frame.setStyleSheet("QFrame { background-color: #252526; border-radius: 8px; border: 1px solid #3e3e42; }")
        col3_layout = QVBoxLayout(col3_frame)
        col3_layout.setContentsMargins(10, 10, 10, 10)
        
        lbl_prev = QLabel("3. Preview & Details")
        lbl_prev.setStyleSheet("font-weight: bold; font-size: 1.1em; border: none;")
        col3_layout.addWidget(lbl_prev)
        
        self.lbl_preview = QLabel("Select an image to preview")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet("background-color: #1e1e1e; border: 1px solid #454545; color: #666; border-radius: 4px;")
        self.lbl_preview.setMinimumHeight(200)
        col3_layout.addWidget(self.lbl_preview, stretch=1)
        
        details_form = QVBoxLayout()
        
        details_form.addWidget(QLabel("Manga/Comic Title:", styleSheet="border: none;"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Enter a unique title...")
        details_form.addWidget(self.title_input)
        
        details_form.addWidget(QLabel("Custom Tags (comma separated):", styleSheet="border: none; margin-top: 10px;"))
        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("e.g. Creator Name, Character")
        details_form.addWidget(self.tags_input)
        
        self.btn_create = QPushButton("Create Comic/Manga")
        self.btn_create.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_create.setStyleSheet("QPushButton { font-size: 1.1em; background-color: #8957e5; color: white; border-radius: 4px; font-weight: bold; padding: 12px; margin-top: 15px;} QPushButton:hover { background-color: #9c67fa; }")
        self.btn_create.clicked.connect(self.create_manga)
        details_form.addWidget(self.btn_create)
        
        col3_layout.addLayout(details_form)
        columns_splitter.addWidget(col3_frame)
        
        columns_splitter.setStretchFactor(0, 1)
        columns_splitter.setStretchFactor(1, 1)
        columns_splitter.setStretchFactor(2, 1)

        main_layout.addWidget(columns_splitter)

    def import_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Import")
        if folder:
            try:
                valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
                
                entries = list(os.scandir(folder))
                has_subdirs = any(e.is_dir() for e in entries)
                
                if not has_subdirs:
                    images = sorted([e.path for e in entries if e.is_file() and e.name.lower().endswith(valid_exts)], key=lambda p: natural_key(os.path.basename(p)))
                    if images:
                        for path in images:
                            if path not in self.selected_images:
                                self.selected_images.append(path)
                                self.add_to_org_list(path)
                else:
                    leaf_folders = []
                    for dirpath, dirnames, filenames in os.walk(folder):
                        images = [os.path.join(dirpath, f) for f in filenames if f.lower().endswith(valid_exts)]
                        if images:
                            images = sorted(images, key=lambda p: natural_key(os.path.basename(p)))
                            leaf_folders.append({
                                'name': os.path.basename(dirpath),
                                'path': dirpath,
                                'images': images
                            })
                            
                    if leaf_folders:
                        self.last_imported_leaf_folders = leaf_folders
                        self.is_grouped = True
                        
                        import sys
                        base = getattr(sys, '_MEIPASS', os.path.abspath("."))
                        from PyQt6.QtGui import QIcon
                        self.btn_group_toggle.setIcon(QIcon(os.path.join(base, "assets", "uisvg", "ungroup.svg")))
                        self.btn_group_toggle.setToolTip("Ungroup Folders")
                        self.btn_group_toggle.show()
                        
                        self.render_batch_import()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to read directory: {e}")

    def toggle_group(self):
        self.is_grouped = not self.is_grouped
        import sys
        base = getattr(sys, '_MEIPASS', os.path.abspath("."))
        from PyQt6.QtGui import QIcon
        if self.is_grouped:
            self.btn_group_toggle.setIcon(QIcon(os.path.join(base, "assets", "uisvg", "ungroup.svg")))
            self.btn_group_toggle.setToolTip("Ungroup Folders")
        else:
            self.btn_group_toggle.setIcon(QIcon(os.path.join(base, "assets", "uisvg", "group.svg")))
            self.btn_group_toggle.setToolTip("Group Folders")
            
        self.render_batch_import()
        
    def render_batch_import(self):
        leaf_folders = self.last_imported_leaf_folders
        if not leaf_folders:
            return
            
        conn = self.parent_dialog.shared_conn
        cursor = conn.cursor()
        cursor.execute("SELECT manga_id, title FROM CustomMangas")
        existing_mangas = {row[1]: row[0] for row in cursor.fetchall()}
        
        skipped_folders = []
        paths_to_thumb = []
        
        self.search_list.blockSignals(True)
        self.search_list.clear()
        
        if self.is_grouped:
            self.search_list.setViewMode(QListWidget.ViewMode.ListMode)
            for sub in leaf_folders:
                sub_images = sub['images']
                sub_name = sub['name']
                sub_path = sub['path']
                
                if sub_name in existing_mangas:
                    m_id = existing_mangas[sub_name]
                    cursor.execute("SELECT COUNT(*) FROM CustomMangaPages WHERE manga_id = ?", (m_id,))
                    db_page_count = cursor.fetchone()[0]
                    if len(sub_images) == db_page_count:
                        cursor.execute("SELECT tag_name FROM CustomMangaTags WHERE manga_id = ?", (m_id,))
                        tags = [r[0] for r in cursor.fetchall()]
                        skipped_folders.append((sub_name, tags))
                        continue
                
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, sub_path)
                item.setData(Qt.ItemDataRole.UserRole + 1, "folder")
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                
                widget = FolderItemWidget(sub_name, sub_images)
                item.setSizeHint(widget.sizeHint())
                
                self.search_list.addItem(item)
                self.search_list.setItemWidget(item, widget)
                
                paths_to_thumb.extend(sub_images[:10])
        else:
            self.search_list.setViewMode(QListWidget.ViewMode.IconMode)
            from PyQt6.QtGui import QIcon, QPixmap
            empty_pixmap = QPixmap(180, 180)
            empty_pixmap.fill(Qt.GlobalColor.transparent)
            empty_icon = QIcon(empty_pixmap)
            
            for sub in leaf_folders:
                sub_images = sub['images']
                sub_name = sub['name']
                
                if sub_name in existing_mangas:
                    m_id = existing_mangas[sub_name]
                    cursor.execute("SELECT COUNT(*) FROM CustomMangaPages WHERE manga_id = ?", (m_id,))
                    db_page_count = cursor.fetchone()[0]
                    if len(sub_images) == db_page_count:
                        cursor.execute("SELECT tag_name FROM CustomMangaTags WHERE manga_id = ?", (m_id,))
                        tags = [r[0] for r in cursor.fetchall()]
                        skipped_folders.append((sub_name, tags))
                        continue
                        
                for path in sub_images:
                    item = QListWidgetItem()
                    item.setToolTip(os.path.basename(path))
                    item.setData(Qt.ItemDataRole.UserRole, path)
                    item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                    item.setIcon(empty_icon)
                    
                    if path in self.selected_images:
                        item.setSelected(True)
                        
                    self.search_list.addItem(item)
                    paths_to_thumb.append(path)
                    
        self.search_list.blockSignals(False)
        if paths_to_thumb:
            self.thumb_thread.add_to_queue(paths_to_thumb)
            
        if skipped_folders and self.is_grouped:
            if len(skipped_folders) == 1:
                fname, ftags = skipped_folders[0]
                msg = f"This '{fname}' already exists and is tagged with: {', '.join(ftags)}"
            else:
                msg = f"Skipped {len(skipped_folders)} already-tagged folders."
            
            if not hasattr(self, 'snackbar'):
                self.snackbar = Snackbar(self)
            self.snackbar.show_message(msg, 6000)

    def perform_search(self):
        query = self.search_input.text().strip()
        if not query:
            return
            
        self.current_search_id = getattr(self, 'current_search_id', 0) + 1
        
        if hasattr(self, 'thumb_thread'):
            self.thumb_thread.clear_queue()
            
        self.search_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.search_list.blockSignals(True)
        self.search_list.clear()
        self.search_list.blockSignals(False)
        
        if not hasattr(self, 'old_workers'):
            self.old_workers = []
        if hasattr(self, 'search_worker') and self.search_worker is not None:
            self.old_workers.append(self.search_worker)
        self.old_workers = [w for w in getattr(self, 'old_workers', []) if w.isRunning()]
        
        try:
            from Src.Logic.app import DatabaseSearchWorker
            self.loading_bar.show()
            self.search_worker = DatabaseSearchWorker(self.db_path, query, 500, 0, self.current_search_id, "Images")
            self.search_worker.search_finished.connect(self.on_search_finished)
            self.search_worker.start()
        except Exception as e:
            print(f"Search error: {e}")
            self.loading_bar.hide()

    def on_search_finished(self, valid_results, folders_map, search_text, is_appending, search_id):
        if hasattr(self, 'current_search_id') and search_id != self.current_search_id:
            return
            
        self.loading_bar.hide()
        self.search_list.blockSignals(True)
        valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
        
        from PyQt6.QtGui import QIcon, QPixmap
        empty_pixmap = QPixmap(180, 180)
        empty_pixmap.fill(Qt.GlobalColor.transparent)
        empty_icon = QIcon(empty_pixmap)
        
        paths_to_thumb = []
        for path, name, media_type in valid_results:
            if media_type == "image" and os.path.exists(path) and os.path.isfile(path) and path.lower().endswith(valid_exts):
                item = QListWidgetItem()
                item.setToolTip(os.path.basename(path))
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                item.setIcon(empty_icon)
                
                if path in self.selected_images:
                    item.setSelected(True)
                    
                self.search_list.addItem(item)
                paths_to_thumb.append(path)
                
        self.search_list.blockSignals(False)
        if paths_to_thumb:
            self.thumb_thread.add_to_queue(paths_to_thumb)

    def on_thumbnail_ready(self, path, qimage):
        from PyQt6.QtGui import QIcon, QPixmap
        for i in range(self.search_list.count()):
            item = self.search_list.item(i)
            
            if item.data(Qt.ItemDataRole.UserRole + 1) == "folder":
                widget = self.search_list.itemWidget(item)
                if widget and hasattr(widget, 'image_labels'):
                    if path in widget.image_labels:
                        pixmap = QPixmap.fromImage(qimage).scaled(60, 80, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                        widget.image_labels[path].setPixmap(pixmap)
                        return
            else:
                if item.data(Qt.ItemDataRole.UserRole) == path:
                    item.setIcon(QIcon(QPixmap.fromImage(qimage)))
                    break

    def on_search_selection_changed(self):
        selected_items = self.search_list.selectedItems()
        
        is_folder_mode = False
        for item in selected_items:
            if item.data(Qt.ItemDataRole.UserRole + 1) == "folder":
                is_folder_mode = True
                break
                
        if not selected_items and self.search_list.count() > 0:
            if self.search_list.item(0).data(Qt.ItemDataRole.UserRole + 1) == "folder":
                self.org_list.clear()
                self.selected_images.clear()
                self.title_input.clear()
                return

        if is_folder_mode:
            self.org_list.clear()
            self.selected_images.clear()
            valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
            
            for item in selected_items:
                if item.data(Qt.ItemDataRole.UserRole + 1) == "folder":
                    folder_path = item.data(Qt.ItemDataRole.UserRole)
                    try:
                        entries = sorted(os.scandir(folder_path), key=lambda e: natural_key(e.name))
                        for entry in entries:
                            if entry.is_file() and entry.name.lower().endswith(valid_exts):
                                self.selected_images.append(entry.path)
                                self.add_to_org_list(entry.path)
                    except Exception:
                        pass
                        
            if selected_items:
                folder_name = os.path.basename(selected_items[-1].data(Qt.ItemDataRole.UserRole))
                self.title_input.setText(folder_name)
                if self.org_list.count() > 0:
                    self.org_list.setCurrentRow(0)
            return

        selected_in_search = set(item.data(Qt.ItemDataRole.UserRole) for item in selected_items)
        
        visible_in_search = set(self.search_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.search_list.count()))
        
        for path in selected_in_search:
            if path not in self.selected_images:
                self.selected_images.append(path)
                self.add_to_org_list(path)
                
        for path in visible_in_search:
            if path in self.selected_images and path not in selected_in_search:
                self.selected_images.remove(path)
                for i in range(self.org_list.count() - 1, -1, -1):
                    if self.org_list.item(i).data(Qt.ItemDataRole.UserRole) == path:
                        self.org_list.takeItem(i)
                        break

        self.search_list.viewport().update()

    def add_to_org_list(self, path, is_attached=False):
        item = QListWidgetItem(os.path.basename(path))
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setData(Qt.ItemDataRole.UserRole + 2, is_attached)
        self.org_list.addItem(item)

    def move_up(self):
        row = self.org_list.currentRow()
        if row > 0:
            item = self.org_list.takeItem(row)
            self.org_list.insertItem(row - 1, item)
            self.org_list.setCurrentRow(row - 1)
            self._update_selected_images_order()

    def move_down(self):
        row = self.org_list.currentRow()
        if row < self.org_list.count() - 1 and row >= 0:
            item = self.org_list.takeItem(row)
            self.org_list.insertItem(row + 1, item)
            self.org_list.setCurrentRow(row + 1)
            self._update_selected_images_order()

    def remove_item(self):
        row = self.org_list.currentRow()
        if row >= 0:
            item = self.org_list.takeItem(row)
            path = item.data(Qt.ItemDataRole.UserRole)
            if path in self.selected_images:
                self.selected_images.remove(path)
            
            self.search_list.blockSignals(True)
            for i in range(self.search_list.count()):
                search_item = self.search_list.item(i)
                if search_item.data(Qt.ItemDataRole.UserRole) == path:
                    search_item.setSelected(False)
                    break
            self.search_list.blockSignals(False)
        self.search_list.viewport().update()

    def _update_selected_images_order(self):
        self.selected_images.clear()
        for i in range(self.org_list.count()):
            self.selected_images.append(self.org_list.item(i).data(Qt.ItemDataRole.UserRole))
        self.search_list.viewport().update()

    def on_org_item_selected(self, current, previous):
        if not current:
            self.lbl_preview.setText("Select an image to preview")
            self.lbl_preview.setPixmap(QPixmap())
            self.current_preview_path = None
            return
            
        path = current.data(Qt.ItemDataRole.UserRole)
        self.current_preview_path = path
        self.preview_timer.start()

    def show_org_context_menu(self, pos):
        item = self.org_list.itemAt(pos)
        if not item:
            return
            
        row = self.org_list.row(item)
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #252526; color: #d4d4d4; border: 1px solid #333; }"
                           "QMenu::item { padding: 6px 24px 6px 24px; background: transparent; }"
                           "QMenu::item:selected { background-color: #0e639c; }")
                           
        is_attached = item.data(Qt.ItemDataRole.UserRole + 2)
        is_attached_to_prev = False
        if row > 0:
            prev_item = self.org_list.item(row - 1)
            if prev_item:
                is_attached_to_prev = prev_item.data(Qt.ItemDataRole.UserRole + 2)
        
        if is_attached:
            action = menu.addAction("Detach from Next Page")
            action.triggered.connect(lambda: self.set_attached_state(item, False))
        else:
            if row < self.org_list.count() - 1:
                action = menu.addAction("Attach to Next Page (Double Spread)")
                action.triggered.connect(lambda: self.set_attached_state(item, True))
                
        if is_attached_to_prev:
            action2 = menu.addAction("Detach from Previous Page")
            action2.triggered.connect(lambda r=row: self.set_attached_state(self.org_list.item(r - 1), False))
                
        menu.exec(self.org_list.mapToGlobal(pos))
        
    def set_attached_state(self, item, state):
        item.setData(Qt.ItemDataRole.UserRole + 2, state)
        self.org_list.viewport().update()

    def load_preview_image(self):
        path = getattr(self, 'current_preview_path', None)
        if not path or not os.path.exists(path):
            self.lbl_preview.setText("Could not load preview")
            self.lbl_preview.setPixmap(QPixmap())
            return
            
        try:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid():
                target_w = self.lbl_preview.width() - 20
                target_h = self.lbl_preview.height() - 20
                if target_w > 0 and target_h > 0:
                    reader.setScaledSize(size.scaled(target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio))
                img = reader.read()
                if not img.isNull():
                    self.lbl_preview.setPixmap(QPixmap.fromImage(img))
                    return
        except:
            pass
        self.lbl_preview.setText("Could not load preview")
        self.lbl_preview.setPixmap(QPixmap())

    def clear_manga_state(self):
        self.loaded_manga_id = None
        self.title_input.clear()
        self.tags_input.clear()
        self.selected_images.clear()
        self.org_list.clear()
        self.search_list.clear()
        self.search_input.clear()
        self.btn_group_toggle.hide()
        self.lbl_preview.setText("Select an image to preview")
        self.lbl_preview.setPixmap(QPixmap())
        self.btn_create.setText("Create Comic/Manga")
        
    def load_existing_manga(self):
        from Src.Dialogs.load_manga_dialog import LoadMangaDialog
        dialog = LoadMangaDialog(self.db_path, self)
        if dialog.exec():
            manga_id = dialog.selected_manga_id
            if manga_id:
                self.load_manga_data(manga_id)

    def load_manga_data(self, manga_id):
        try:
            conn = self.parent_dialog.shared_conn
            cursor = conn.cursor()
            
            try:
                cursor.execute("ALTER TABLE CustomMangaPages ADD COLUMN attached_to_next BOOLEAN DEFAULT 0")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            
            cursor.execute("SELECT title FROM CustomMangas WHERE manga_id = ?", (manga_id,))
            row = cursor.fetchone()
            if not row:
                return
            title = row[0]
            
            cursor.execute("SELECT tag_name FROM CustomMangaTags WHERE manga_id = ?", (manga_id,))
            tags = [r[0] for r in cursor.fetchall()]
            
            cursor.execute("SELECT image_path, attached_to_next FROM CustomMangaPages WHERE manga_id = ? ORDER BY page_number ASC", (manga_id,))
            pages = cursor.fetchall()
            
            self.clear_manga_state()
            self.loaded_manga_id = manga_id
            self.title_input.setText(title)
            self.tags_input.setText(", ".join(tags))
            
            for path, is_attached in pages:
                self.selected_images.append(path)
                self.add_to_org_list(path, bool(is_attached))
                
            self.btn_create.setText("Save Changes")
            
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load manga data:\n{e}")

    def create_manga(self):
        if not self.db_path or not os.path.exists(self.db_path):
            QMessageBox.warning(self, "Error", "Database not configured.")
            return
            
        title = self.title_input.text().strip()
        if not title:
            QMessageBox.warning(self, "Missing Title", "Please provide a title for the comic/manga.")
            return
            
        self._update_selected_images_order()
            
        if not self.selected_images:
            QMessageBox.warning(self, "Empty Manga", "Please add at least one page to the manga.")
            return
            
        tags = []
        for t in self.tags_input.text().split(','):
            t = t.strip()
            if ':' in t:
                t = t.split(':', 1)[1].strip()
            if t:
                tags.append(t)
        cover = self.selected_images[0]
        
        try:
            conn = self.parent_dialog.shared_conn
            cursor = conn.cursor()
            
            try:
                cursor.execute("ALTER TABLE CustomMangaPages ADD COLUMN attached_to_next BOOLEAN DEFAULT 0")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            

            if self.loaded_manga_id is None:
                cursor.execute("SELECT manga_id FROM CustomMangas WHERE title = ?", (title,))
                if cursor.fetchone():
                    QMessageBox.warning(self, "Duplicate Title", f"A manga named '{title}' already exists.")
                    conn.close()
                    return
                    
                cursor.execute("INSERT INTO CustomMangas (title, cover_image) VALUES (?, ?)", (title, cover))
                manga_id = cursor.lastrowid
                
            else:
                manga_id = self.loaded_manga_id
                cursor.execute("SELECT manga_id FROM CustomMangas WHERE title = ? AND manga_id != ?", (title, manga_id))
                if cursor.fetchone():
                    QMessageBox.warning(self, "Duplicate Title", f"Another manga named '{title}' already exists.")
                    conn.close()
                    return
                
                cursor.execute("UPDATE CustomMangas SET title = ?, cover_image = ? WHERE manga_id = ?", (title, cover, manga_id))
                
                cursor.execute("DELETE FROM CustomMangaPages WHERE manga_id = ?", (manga_id,))
                cursor.execute("DELETE FROM CustomMangaTags WHERE manga_id = ?", (manga_id,))

            page_records = []
            for i in range(self.org_list.count()):
                item = self.org_list.item(i)
                path = item.data(Qt.ItemDataRole.UserRole)
                is_attached = bool(item.data(Qt.ItemDataRole.UserRole + 2))
                page_records.append((manga_id, path, i + 1, is_attached))
                
            cursor.executemany("INSERT INTO CustomMangaPages (manga_id, image_path, page_number, attached_to_next) VALUES (?, ?, ?, ?)", page_records)
            
            if tags:
                tag_records = [(manga_id, tag) for tag in tags]
                cursor.executemany("INSERT INTO CustomMangaTags (manga_id, tag_name) VALUES (?, ?)", tag_records)
                
            conn.commit()
            
            if self.loaded_manga_id is None:
                QMessageBox.information(self, "Success", f"Comic/Manga '{title}' created successfully!")
            else:
                QMessageBox.information(self, "Success", f"Comic/Manga '{title}' updated successfully!")
            
            try:
                main_app = self.parent_dialog.parent()
                if hasattr(main_app, "reload_autocomplete_tags"):
                    main_app.reload_autocomplete_tags()
            except Exception:
                pass
            
            self.clear_manga_state()
            
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to save manga:\n{e}")
