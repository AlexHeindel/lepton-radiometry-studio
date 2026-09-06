import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
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


def test_extrema_markers_can_be_hidden() -> None:
    app = QApplication.instance() or QApplication([])
    canvas = ThermalCanvas()

    assert canvas.show_extrema is True
    canvas.set_show_extrema(False)
    app.processEvents()
    assert canvas.show_extrema is False


def test_zoom_preserves_source_coordinate_mapping_and_measurements() -> None:
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

    canvas.add_point_marker(80, 60)
    canvas.add_region("rectangle", 60, 40, 100, 80)
    canvas.zoom_in()
    app.processEvents()

    assert canvas.zoom == 1.25
    assert canvas.widget_to_pixel(QPointF(400.0, 300.0)) == (80, 60)
    assert canvas.point_markers[0].x == 80
    assert canvas.regions[0].bounds == (60, 40, 100, 80)

    canvas.reset_view()
    assert canvas.zoom == 1.0
    canvas.close()


def test_undo_and_clear_manage_persistent_measurements() -> None:
    app = QApplication.instance() or QApplication([])
    canvas = ThermalCanvas()
    frame = ThermalFrame(raw=np.zeros((2, 3), dtype=np.uint16), timestamp_ns=1)
    canvas.set_frame(frame, render_frame(frame))

    canvas.add_point_marker(1, 1)
    canvas.add_region("circle", 0, 0, 2, 1)
    canvas.undo_last_measurement()
    assert len(canvas.point_markers) == 1
    assert not canvas.regions

    canvas.clear_measurements()
    assert not canvas.point_markers
    app.processEvents()


def test_inspect_mode_left_drag_pans_and_marker_mode_takes_precedence() -> None:
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
    canvas.zoom_in()

    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(400.0, 300.0),
        QPointF(400.0, 300.0),
        QPointF(400.0, 300.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(500.0, 300.0),
        QPointF(500.0, 300.0),
        QPointF(500.0, 300.0),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(500.0, 300.0),
        QPointF(500.0, 300.0),
        QPointF(500.0, 300.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    original_center_x = canvas._view_center.x()
    canvas.mousePressEvent(press)
    canvas.mouseMoveEvent(move)
    canvas.mouseReleaseEvent(release)

    assert canvas._view_center.x() < original_center_x
    assert canvas._pan_last is None

    canvas.set_interaction_mode("point")
    canvas.mousePressEvent(press)
    assert len(canvas.point_markers) == 1
    assert canvas._pan_last is None
    with pytest.raises(ValueError):
        canvas.set_interaction_mode("pan")
    canvas.close()
