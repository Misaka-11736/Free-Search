from pathlib import Path
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from free_search.ui import SearchWindow

app = QApplication([])
font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
if font.exists():
    font_id = QFontDatabase.addApplicationFont(str(font))
    families = QFontDatabase.applicationFontFamilies(font_id)
    if families:
        app.setFont(QFont(families[0], 10))
window = SearchWindow(ROOT / "private/ui-check", ROOT / "models", "offline")
window.show()
deadline = time.monotonic() + 30
while window.job and window.job.isRunning() and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(.05)
app.processEvents()
window.grab().save(str(ROOT / "private/ui-preview.png"))
if window.job and window.job.isRunning():
    raise RuntimeError("UI startup inspection did not finish")
window.close()
print("UI startup, inspection, render, and close passed.")
