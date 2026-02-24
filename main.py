# main.py
import sys
from PyQt6.QtWidgets import QApplication
from Src.Logic.app import MediaExplorerApp

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    window = MediaExplorerApp()
    window.show()
    
    sys.exit(app.exec())