import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from lepton_radiometry_studio.domain import ThermalFrame
from lepton_radiometry_studio.processing import render_frame
from lepton_radiometry_studio.ui.thermal_canvas import ThermalCanvas


def test_widget_coordinates_map_to_exact_source_pixels() -> None:
    app = QApplication.instance() or QApplication([])
    canvas = ThermalCanvas()
    canvas.resize(800, 600)
    frame = ThermalFrame(
        raw=np.arange(120 * 160, dtype=np.uint16).reshape(120, 160),
        timestamp_ns=1,
    )
    canvas.set_frame(frame, render_frame(frame))
    canvas.show()
    app.processEvents()

    assert canvas.widget_to_pixel(QPointF(0.1, 0.1)) == (0, 0)
    assert canvas.widget_to_pixel(QPointF(400.0, 300.0)) == (80, 60)
    assert canvas.widget_to_pixel(QPointF(799.9, 599.9)) == (159, 119)
    assert canvas.widget_to_pixel(QPointF(-1.0, 300.0)) is None

    canvas.close()

