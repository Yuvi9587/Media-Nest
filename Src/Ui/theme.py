# Src/Ui/theme.py

VSCODE_DARK_THEME = """
QMainWindow { background-color: #1e1e1e; }

QWidget { 
    background-color: #1e1e1e; 
    color: #cccccc; 
    font-family: 'Segoe UI', sans-serif; 
    font-size: 13px; 
}

/* Sidebar Styling */
QTreeView { 
    background-color: #252526; 
    border: none; 
    padding-top: 5px; 
}
QTreeView::item { padding: 4px; }
QTreeView::item:hover { background-color: #2a2d2e; }
QTreeView::item:selected { background-color: #37373d; color: #ffffff; }

/* Header / Button Styling */
QFrame { background-color: #252526; }

QPushButton { 
    background-color: #0e639c; 
    color: white; 
    border: none; 
    padding: 6px 12px; 
    text-align: left; 
    font-weight: bold; 
}
QPushButton:hover { background-color: #1177bb; }

/* Scroll Area */
QScrollArea { border: none; background-color: #1e1e1e; }
QLabel { background-color: #1e1e1e; }

/* --- Splitter Handles (The draggable dividers) --- */
QSplitter::handle {
    background-color: #181818; 
}
QSplitter::handle:horizontal {
    width: 3px; 
}
QSplitter::handle:vertical {
    height: 3px;
}
QSplitter::handle:hover {
    background-color: #0e639c; 
}
"""
