import os
import sqlite3
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QListWidget, QPushButton, 
                             QHBoxLayout, QLabel, QMessageBox, QListWidgetItem, QMenu)
from PyQt6.QtCore import Qt

class LoadMangaDialog(QDialog):
    def __init__(self, db_path, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.selected_manga_id = None
        self.selected_manga_title = None
        
        self.setWindowTitle("Load Existing")
        self.resize(400, 500)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        self.setup_ui()
        self.load_mangas()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        lbl = QLabel("Select a Manga to Edit:")
        lbl.setStyleSheet("font-size: 1.1em; font-weight: bold;")
        layout.addWidget(lbl)
        
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            "QListWidget { background-color: #252526; border: 1px solid #3e3e42; border-radius: 4px; padding: 5px; }"
            "QListWidget::item { padding: 8px; border-bottom: 1px solid #333; }"
            "QListWidget::item:selected { background-color: #0e639c; }"
        )
        self.list_widget.itemDoubleClicked.connect(self.accept_selection)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.list_widget)
        
        btn_layout = QHBoxLayout()
        self.btn_load = QPushButton("Load")
        self.btn_load.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_load.setStyleSheet("background-color: #0e639c; color: white; padding: 8px; font-weight: bold; border-radius: 4px;")
        self.btn_load.clicked.connect(self.accept_selection)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setStyleSheet("background-color: #454545; color: white; padding: 8px; font-weight: bold; border-radius: 4px;")
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_load)
        
        layout.addLayout(btn_layout)

    def load_mangas(self):
        if not self.db_path or not os.path.exists(self.db_path):
            QMessageBox.warning(self, "Error", "Database not found.")
            return
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT m.manga_id, m.title, COUNT(p.page_number) as page_count
                FROM CustomMangas m
                LEFT JOIN CustomMangaPages p ON m.manga_id = p.manga_id
                GROUP BY m.manga_id
                ORDER BY m.title COLLATE NOCASE ASC
            ''')
            
            mangas = cursor.fetchall()
            conn.close()
            
            for manga_id, title, page_count in mangas:
                display_text = f"{title} ({page_count} pages)"
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, (manga_id, title))
                self.list_widget.addItem(item)
                
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to load mangas:\n{e}")

    def accept_selection(self):
        selected = self.list_widget.currentItem()
        if selected:
            manga_id, title = selected.data(Qt.ItemDataRole.UserRole)
            self.selected_manga_id = manga_id
            self.selected_manga_title = title
            self.accept()
        else:
            QMessageBox.warning(self, "No Selection", "Please select a manga to load.")

    def show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
            
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #252526; color: #d4d4d4; border: 1px solid #333; }"
                           "QMenu::item { padding: 6px 24px 6px 24px; background: transparent; }"
                           "QMenu::item:selected { background-color: #0e639c; }")
        
        delete_action = menu.addAction("Delete Manga Entry")
        action = menu.exec(self.list_widget.mapToGlobal(pos))
        
        if action == delete_action:
            self.delete_manga(item)

    def delete_manga(self, item):
        manga_id, title = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, 
            "Confirm Delete", 
            f"Are you sure you want to delete the manga entry '{title}'?\nThis will not delete the actual image files.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute("DELETE FROM CustomMangas WHERE manga_id = ?", (manga_id,))
                cursor.execute("DELETE FROM CustomMangaPages WHERE manga_id = ?", (manga_id,))
                cursor.execute("DELETE FROM CustomMangaTags WHERE manga_id = ?", (manga_id,))
                
                conn.commit()
                conn.close()
                
                row = self.list_widget.row(item)
                self.list_widget.takeItem(row)
                
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to delete manga:\n{e}")
