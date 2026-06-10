import sys
import os
import json
import ctypes




if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.abspath(".")

config_path = os.path.join(base_dir, "config.json")

try:
    with open(config_path, "r") as f:
        config = json.load(f)
        scale_value = config.get("ui_scale", "1.0")
        try:
            if float(scale_value) < 0.4:
                scale_value = "0.4"
        except (ValueError, TypeError):
            scale_value = "1.0"
        scale_value = str(scale_value)
except Exception:
    scale_value = "1.0"

os.environ["QT_SCALE_FACTOR"] = scale_value
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"


from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from Src.Logic.paths import resource_path


try:

    myappid = 'mycompany.medianest.app.v1'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception as e:
    print(f"Shell32 AppID Error: {e}")


app = QApplication(sys.argv)


icon_path = resource_path(os.path.join("assets", "Logo.ico"))
if os.path.exists(icon_path):
    app_icon = QIcon(icon_path)
    app.setWindowIcon(app_icon)
else:
    print(f"CRITICAL: Could not find icon at {icon_path}")


from Src.Logic.app import MediaExplorerApp
window = MediaExplorerApp()


if os.path.exists(icon_path):
    window.setWindowIcon(app_icon)

window.show()
sys.exit(app.exec())