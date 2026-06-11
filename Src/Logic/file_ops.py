import os
import shutil
import subprocess
import platform
import time
from PyQt6.QtWidgets import QMenu, QMessageBox, QApplication
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QObject, QUrl, QMimeData

class FileContextMenu(QObject):
    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance  
        self.is_cut = False
        self.internal_cut_path = None

    def show_menu(self, global_position, widget, selected_path, current_folder):
        menu = QMenu(widget)
        
        menu.setStyleSheet("""
            QMenu { background-color: #252526; color: #cccccc; border: 1px solid #3e3e42; padding: 5px 0px; }
            QMenu::item { padding: 5px 25px 5px 20px; }
            QMenu::item:selected { background-color: #004578; color: white; }
            QMenu::separator { height: 1px; background-color: #3e3e42; margin: 4px 0px; }
        """)

        action_copy = QAction("Copy", widget)
        action_cut = QAction("Cut", widget)
        action_paste = QAction("Paste", widget)
        action_delete = QAction("Delete", widget)
        action_open = QAction("Open in Explorer", widget)
        action_file_info = QAction("ℹ File Info", widget)

        if not selected_path:
            action_copy.setEnabled(False)
            action_cut.setEnabled(False)
            action_delete.setEnabled(False)
            action_open.setEnabled(False)
            action_file_info.setEnabled(False)

        clipboard = QApplication.clipboard()
        if not clipboard.mimeData().hasUrls() or current_folder == "VIRTUAL_BLOCK":
            action_paste.setEnabled(False)

        action_copy.triggered.connect(lambda: self.on_copy(selected_path))
        action_cut.triggered.connect(lambda: self.on_cut(selected_path))
        action_paste.triggered.connect(lambda: self.on_paste(current_folder))
        action_delete.triggered.connect(lambda: self.on_delete(selected_path))
        action_open.triggered.connect(lambda: self.on_open_in_explorer(selected_path))
        action_file_info.triggered.connect(lambda: self.on_show_file_info(selected_path))

        menu.addAction(action_copy)
        menu.addAction(action_cut)
        menu.addAction(action_paste)
        menu.addSeparator()
        menu.addAction(action_delete)
        menu.addSeparator()
        menu.addAction(action_open)
        menu.addSeparator()
        menu.addAction(action_file_info)

        menu.exec(global_position)

    def on_copy(self, path):
        if not path: return
        clipboard = QApplication.clipboard()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path)])
        clipboard.setMimeData(mime)
        
        self.is_cut = False
        self.internal_cut_path = None

    def on_cut(self, path):
        if not path: return
        self.on_copy(path)
        self.is_cut = True
        self.internal_cut_path = path

    def on_paste(self, target_folder):
        if not target_folder: return
        
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        if not mime.hasUrls(): return

        for url in mime.urls():
            if url.isLocalFile():
                src_path = url.toLocalFile()
                filename = os.path.basename(src_path)
                dest_path = os.path.join(target_folder, filename)

                if src_path == dest_path: continue

                try:
                    if self.is_cut and self.internal_cut_path == src_path:
                        if hasattr(self.app, 'release_media_file'):
                            self.app.release_media_file(path)
                            QApplication.processEvents()
                            QApplication.processEvents()

                            time.sleep(0.1)
                            
                        max_retries = 10
                        for i in range(max_retries):
                            try:
                                shutil.move(src_path, dest_path)
                                break
                            except PermissionError as e:
                                if i == max_retries - 1: raise e
                                time.sleep(0.05)
                                
                        self.is_cut = False
                        self.internal_cut_path = None
                    else:
                        if os.path.isdir(src_path):
                            shutil.copytree(src_path, dest_path)
                        else:
                            shutil.copy2(src_path, dest_path)
                except Exception as e:
                    QMessageBox.critical(None, "Paste Error", f"Failed to paste:\n{str(e)}")

        if hasattr(self.app, 'refresh_folder_ui'):
            self.app.refresh_folder_ui(target_folder)

    def on_delete(self, path):
        if not path or not os.path.exists(path): return
            
        filename = os.path.basename(path)
        reply = QMessageBox.question(
            None, 'Confirm Delete', f"Are you sure you want to permanently delete:\n{filename}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if hasattr(self.app, 'release_media_file'):
                    self.app.release_media_file(path)
                    QApplication.processEvents()
                    time.sleep(0.05)

                max_retries = 20
                for i in range(max_retries):
                    try:
                        if os.path.isdir(path):
                            shutil.rmtree(path)
                        else:
                            os.remove(path)
                        break
                    except PermissionError as e:
                        if i == max_retries - 1: 
                            raise e
                        time.sleep(0.1)
                
                if hasattr(self.app, 'refresh_folder_ui'):
                    parent_dir = os.path.dirname(path)
                    self.app.refresh_folder_ui(parent_dir)
                    
            except Exception as e:
                QMessageBox.critical(None, "Delete Error", f"Failed to delete:\n{str(e)}")

    def on_open_in_explorer(self, path):
        if not path or not os.path.exists(path): return
        sys_name = platform.system()
        if sys_name == "Windows":
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
        elif sys_name == "Darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])

    def on_show_file_info(self, path):
        """Delegates to the app to show the file info panel."""
        if not path: return
        if hasattr(self.app, 'show_file_info_panel'):
            self.app.show_file_info_panel(path)