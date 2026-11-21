import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

from .gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("IDEF-SIM Studio")
    app.setStyle("Fusion")
    tr = QTranslator(app)
    tr_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for lang in ("pt_BR",):
        if tr.load(f"qtbase_{lang}", tr_dir):
            app.installTranslator(tr)
            break
    win = MainWindow(sys.argv[1] if len(sys.argv) > 1 else None)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
