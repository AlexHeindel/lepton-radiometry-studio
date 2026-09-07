from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from lepton_radiometry_studio.processing.palettes import PALETTES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lepton-viewer",
        description="Open the lightest-weight live Lepton camera viewer.",
    )
    parser.add_argument(
        "--palette",
        choices=tuple(PALETTES),
        default="Iron",
        help="thermal palette (default: %(default)s)",
    )
    parser.add_argument(
        "--source",
        choices=("camera", "synthetic"),
        default="camera",
        help="live source; synthetic is for hardware-free testing (default: %(default)s)",
    )
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="open full screen; press Escape to close",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    # Keep --help usable without importing Qt. The graphical runtime is loaded
    # only after command-line validation succeeds.
    from PySide6.QtWidgets import QApplication

    from lepton_radiometry_studio.ui.feed_window import FeedWindow

    app = QApplication([sys.argv[0]])
    app.setApplicationName("Lepton Viewer")
    app.setOrganizationName("Lepton Radiometry Studio")
    window = FeedWindow(palette=args.palette, source_kind=args.source)
    if args.fullscreen:
        window.showFullScreen()
    else:
        window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
