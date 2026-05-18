import sys
import os


def resource_path(relative_path):
    """
    Get absolute path to resource.
    Works for:
    - VS Code / normal Python execution
    - PyInstaller --onedir
    - PyInstaller --onefile
    """

    try:
        # PyInstaller temporary folder
        base_path = sys._MEIPASS

    except Exception:
        # Running normally from source
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)