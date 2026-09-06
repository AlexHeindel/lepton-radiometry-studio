from __future__ import annotations

import sys
from typing import Optional, Sequence

from PySide6.QtWidgets import QApplication

from lepton_radiometry_studio.ui.lite_window import LiteMainWindow


def main(argv: Optional[Sequence[str]] = None) -> int:
    app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName("Lepton Radiometry Lite")
    app.setOrganizationName("Lepton Radiometry Studio")
    window = LiteMainWindow()
    window.show()
    return app.exec()
