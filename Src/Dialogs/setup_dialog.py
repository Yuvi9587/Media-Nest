import os
import sys
import sqlite3
import requests
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QFileDialog, QFrame, QMessageBox, QApplication)
from PyQt6.QtCore import Qt, QSettings

class FirstTimeSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Media Nest Setup")
        self.setMinimumWidth(600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        header = QLabel("Welcome to Media Nest!")
        header.setStyleSheet("font-size: 1.5em; font-weight: bold; color: #00a2ff;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        
        lbl_sub = QLabel("How would you like to set up your workspace?")
        lbl_sub.setStyleSheet("font-size: 1.1em; color: #cccccc; margin-bottom: 10px;")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_sub)
        
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame { background-color: #252526; border-radius: 8px; border: 1px solid #3e3e42; padding: 10px; }
            QLabel { border: none; }
        """)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setSpacing(10)

        if getattr(sys, 'frozen', False):
            import sys as _sys
            base_dir = getattr(_sys, '_MEIPASS', os.path.abspath("."))
        else:
            base_dir = os.path.abspath(".")
            
        svg_db = os.path.join(base_dir, "assets", "uisvg", "database.svg").replace("\\", "/")
        svg_tag = os.path.join(base_dir, "assets", "uisvg", "tag.svg").replace("\\", "/")
        svg_tools = os.path.join(base_dir, "assets", "uisvg", "tools.svg").replace("\\", "/")

        info_text = f"""
        <h3 style='color: #ffffff; margin-bottom: 2px;'><img src='{svg_db}' width='16' height='16'> How the Databases Work</h3>
        <ul style='margin-top: 0px;'>
            <li><b>library.db:</b> Your main core. It securely stores all your media paths, hashes, and tags.</li>
            <li><b>character.db:</b> Handles specific character metadata and profiles.</li>
        </ul>
        
        <h3 style='color: #ffffff; margin-bottom: 2px;'><img src='{svg_tag}' width='16' height='16'> The Tagging System</h3>
        <ul style='margin-top: 0px;'>
            <li><b>Automatic Tags:</b> If you link an existing <i>Kemono Downloader</i> database, downloaded images from compatible sites will automatically share their tags!</li>
            <li><b>Manual Tags:</b> When you import local folders or use standalone mode, files go into a 'Tagless Inbox'. You must tag these manually.</li>
        </ul>
        
        <h3 style='color: #ffffff; margin-bottom: 2px;'><img src='{svg_tools}' width='16' height='16'> Where are the Tools?</h3>
        <p style='margin-top: 0px; margin-left: 25px;'>You can access the <b>Tag Manager</b>, <b>Image Deduplication</b>, and <b>Video Deduplication</b> scanners anytime by clicking the <b>Settings</b> button in the main app.</p>
        """
        
        lbl_info = QLabel(info_text)
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet("font-size: 1em; color: #cccccc; line-height: 1.4;")
        lbl_info.setTextFormat(Qt.TextFormat.RichText)
        
        info_layout.addWidget(lbl_info)
        layout.addWidget(info_frame)

        action_layout = QVBoxLayout()
        action_layout.setSpacing(15)
        action_layout.setContentsMargins(0, 15, 0, 0)
        
        self.btn_link_kemono = QPushButton("Link Kemono Downloader Database")
        self.btn_link_kemono.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_link_kemono.setFixedHeight(45)
        self.btn_link_kemono.setStyleSheet("""
            QPushButton { background-color: #8957e5; color: white; font-weight: bold; font-size: 1.1em; border-radius: 6px; border: none; }
            QPushButton:hover { background-color: #9d6ceb; }
        """)
        self.btn_link_kemono.clicked.connect(self.link_kemono_database)

        self.btn_standalone = QPushButton("I don't have Kemono Downloader (Create Portable Database)")
        self.btn_standalone.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_standalone.setFixedHeight(45)
        self.btn_standalone.setStyleSheet("""
            QPushButton { background-color: #007acc; color: white; font-weight: bold; font-size: 1.1em; border-radius: 6px; border: none; }
            QPushButton:hover { background-color: #0098ff; }
        """)
        self.btn_standalone.clicked.connect(self.create_portable_workspace)

        action_layout.addWidget(self.btn_link_kemono)
        action_layout.addWidget(self.btn_standalone)
        
        layout.addLayout(action_layout)
        self.setStyleSheet("QDialog { background-color: #1e1e1e; }")

    def download_character_db(self, target_folder):
        """Downloads the character database if it is missing from the folder."""
        db_path = os.path.join(target_folder, "character.db")
        
        if os.path.exists(db_path):
            return True 

        url = "https://raw.githubusercontent.com/Yuvi63771/Rule34/main/characters.db"
        
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            
            with open(db_path, 'wb') as f:
                f.write(response.content)
                
            QApplication.restoreOverrideCursor()
            return True
            
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(
                self, "Download Warning", 
                f"Could not automatically download 'character.db'.\n\nYou may need to add it to your folder manually later.\nError: {e}"
            )
            return False

    def link_kemono_database(self):
        """Allows the user to locate their existing Kemono workspace and validates it."""
        folder = QFileDialog.getExistingDirectory(self, "Locate your Kemono Downloader Workspace")
        if not folder: return
        
        target_folder = os.path.normpath(folder)
        library_db_path = os.path.join(target_folder, "library.db")
        
        if os.path.exists(library_db_path):
            self.btn_link_kemono.setText("Verifying and downloading assets...")
            self.btn_link_kemono.setEnabled(False)
            QApplication.processEvents()
            
            self.download_character_db(target_folder)
            self.save_and_exit(target_folder, is_new=False)
        else:
            QMessageBox.critical(
                self, "Invalid Folder", 
                f"Could not find 'library.db' in:\n{target_folder}\n\nPlease make sure you are selecting the main Kemono Downloader database folder."
            )

    def create_portable_workspace(self):
        """Creates a 'Database' folder directly next to the Media Nest .exe file."""
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.abspath(".")
            
        new_workspace = os.path.join(base_dir, "Database")
        
        try:
            os.makedirs(new_workspace, exist_ok=True)
            
            self.btn_standalone.setText("Building Workspace and downloading assets...")
            self.btn_standalone.setEnabled(False)
            QApplication.processEvents()
            
            db_path = os.path.join(new_workspace, "library.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("CREATE TABLE IF NOT EXISTS Images (hash TEXT PRIMARY KEY, file_path TEXT, file_name TEXT, phash TEXT)")
            cursor.execute("CREATE TABLE IF NOT EXISTS Tags (tag_id INTEGER PRIMARY KEY AUTOINCREMENT, tag_name TEXT UNIQUE)")
            cursor.execute("CREATE TABLE IF NOT EXISTS ImageTags (hash TEXT, tag_id INTEGER, PRIMARY KEY (hash, tag_id))")
            cursor.execute("CREATE TABLE IF NOT EXISTS tagless (hash TEXT PRIMARY KEY, file_path TEXT, file_name TEXT, phash TEXT)")
            cursor.execute("CREATE TABLE IF NOT EXISTS IgnoredPairs (hash1 TEXT, hash2 TEXT, PRIMARY KEY (hash1, hash2))")
            
            cursor.execute("CREATE TABLE IF NOT EXISTS CustomMangas (manga_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, cover_image TEXT)")
            cursor.execute("CREATE TABLE IF NOT EXISTS CustomMangaPages (manga_id INTEGER, image_path TEXT, page_number INTEGER, PRIMARY KEY (manga_id, page_number))")
            cursor.execute("CREATE TABLE IF NOT EXISTS CustomMangaTags (manga_id INTEGER, tag_name TEXT, PRIMARY KEY (manga_id, tag_name))")
            
            conn.commit()
            conn.close()
            
            self.download_character_db(new_workspace)
            
            self.save_and_exit(new_workspace, is_new=True)
            
        except Exception as e:
            self.btn_standalone.setText("I don't have Kemono Downloader (Create Portable Database)")
            self.btn_standalone.setEnabled(True)
            QMessageBox.critical(self, "Database Error", f"Failed to initialize portable database:\n{e}")

    def save_and_exit(self, path, is_new=False):
        """Saves the path to the Global OS Registry and closes the setup."""
        settings = QSettings("MediaNest", "AppConfig")
        settings.setValue("db_folder_path", path)
        
        if is_new:
            QMessageBox.information(self, "Workspace Created", f"Portable database successfully created at:\n\n{path}")
        else:
            QMessageBox.information(self, "Workspace Linked", f"Database linked successfully!")
            
        self.accept()