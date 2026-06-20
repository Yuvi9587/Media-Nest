import os
import sqlite3
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QListWidget, QListWidgetItem,
                             QScrollArea, QFrame, QFileDialog, QMessageBox, QSplitter, QProgressBar,
                             QStyledItemDelegate)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QImageReader, QPainter, QColor
import re

def natural_key(text):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", text)]

class PageNumberDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        page_num = index.row() + 1
        page_text = f"Pg {page_num}"
        painter.save()
        painter.setPen(QColor("#888888"))
        rect = option.rect
        rect.adjust(0, 0, -10, 0)
        painter.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, page_text)
        painter.restore()


class PaginationTab(QWidget):
    def __init__(self, parent_dialog):
        super().__init__()
        self.parent_dialog = parent_dialog
        self.db_path = parent_dialog.current_db_folder
        if self.db_path:
            self.db_path = os.path.join(self.db_path, "library.db")
            
        self.selected_images = []
        
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

            # Resolve db paths so the completer can query AllTags.db and library.db
            library_db = self.db_path or ""
            alltags_db = ""
            if library_db:
                alltags_db = os.path.join(os.path.dirname(library_db), "AllTags.db")

            # Search input completer (colored by category)
            self.tag_completer = DbLookupCompleter(self)
            self.tag_completer.set_db_paths(alltags_db, library_db)
            self.search_input.setCompleter(self.tag_completer)
            self.search_input.textEdited.connect(self.tag_completer.on_text_changed)
            self.tag_completer.activated.connect(self.on_completer_activated)

            # Ghost-text namespace expander for search input (char→character:, ser→series:, etc.)
            self._search_expander = NsTabExpander(self.search_input, self)
            self.search_input.installEventFilter(self._search_expander)

            # Custom tags input completer (same colored autocomplete)
            self.custom_tags_completer = DbLookupCompleter(self)
            self.custom_tags_completer.set_db_paths(alltags_db, library_db)
            if hasattr(self, 'tags_input'):
                self.tags_input.setCompleter(self.custom_tags_completer)
                self.tags_input.textEdited.connect(self.custom_tags_completer.on_text_changed)

                # Ghost-text namespace expander for custom tags input
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
                entries = sorted(os.scandir(folder), key=lambda e: natural_key(e.name))
                valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
                
                for entry in entries:
                    if entry.is_file() and entry.name.lower().endswith(valid_exts):
                        path = entry.path
                        if path not in self.selected_images:
                            self.selected_images.append(path)
                            self.add_to_org_list(path)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to read directory: {e}")

    def perform_search(self):
        query = self.search_input.text().strip()
        if not query:
            return
            
        self.current_search_id = getattr(self, 'current_search_id', 0) + 1
        
        if hasattr(self, 'thumb_thread'):
            self.thumb_thread.clear_queue()
            
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
            if item.data(Qt.ItemDataRole.UserRole) == path:
                item.setIcon(QIcon(QPixmap.fromImage(qimage)))
                break

    def on_search_selection_changed(self):
        selected_in_search = set(item.data(Qt.ItemDataRole.UserRole) for item in self.search_list.selectedItems())
        
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

    def add_to_org_list(self, path):
        item = QListWidgetItem(os.path.basename(path))
        item.setData(Qt.ItemDataRole.UserRole, path)
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

    def _update_selected_images_order(self):
        self.selected_images.clear()
        for i in range(self.org_list.count()):
            self.selected_images.append(self.org_list.item(i).data(Qt.ItemDataRole.UserRole))

    def on_org_item_selected(self, current, previous):
        if not current:
            self.lbl_preview.setText("Select an image to preview")
            self.lbl_preview.setPixmap(QPixmap())
            self.current_preview_path = None
            return
            
        path = current.data(Qt.ItemDataRole.UserRole)
        self.current_preview_path = path
        self.preview_timer.start()

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
            
            cursor.execute("SELECT title FROM CustomMangas WHERE manga_id = ?", (manga_id,))
            row = cursor.fetchone()
            if not row:
                return
            title = row[0]
            
            cursor.execute("SELECT tag_name FROM CustomMangaTags WHERE manga_id = ?", (manga_id,))
            tags = [r[0] for r in cursor.fetchall()]
            
            cursor.execute("SELECT image_path FROM CustomMangaPages WHERE manga_id = ? ORDER BY page_number ASC", (manga_id,))
            pages = [r[0] for r in cursor.fetchall()]
            
            
            self.clear_manga_state()
            self.loaded_manga_id = manga_id
            self.title_input.setText(title)
            self.tags_input.setText(", ".join(tags))
            
            for path in pages:
                self.selected_images.append(path)
                self.add_to_org_list(path)
                
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
            
        tags = [t.strip() for t in self.tags_input.text().split(',') if t.strip()]
        cover = self.selected_images[0]
        
        try:
            conn = self.parent_dialog.shared_conn
            cursor = conn.cursor()
            
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

            page_records = [(manga_id, path, idx + 1) for idx, path in enumerate(self.selected_images)]
            cursor.executemany("INSERT INTO CustomMangaPages (manga_id, image_path, page_number) VALUES (?, ?, ?)", page_records)
            
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
