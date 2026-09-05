from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Signal, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from lepton_radiometry_studio.domain import (
    PointMarker,
    RegionOfInterest,
    ThermalFrame,
)


class ThermalCanvas(QWidget):
    pixel_hovered = Signal(int, int, int, float)
    hover_left = Signal()
    measurements_changed = Signal()
    zoom_changed = Signal(float)

    _VALID_MODES = {"inspect", "point", "rectangle", "circle", "pan"}

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(480, 360)
        self._frame: Optional[ThermalFrame] = None
        self._image: Optional[QImage] = None
        self._display_rect = QRectF()
        self._minimum_xy: Optional[Tuple[int, int]] = None
        self._maximum_xy: Optional[Tuple[int, int]] = None
        self._show_extrema = True
        self._zoom = 1.0
        self._view_center = QPointF()
        self._interaction_mode = "inspect"
        self._measurement_editing_enabled = True
        self._point_markers: list[PointMarker] = []
        self._regions: list[RegionOfInterest] = []
        self._history: list[Tuple[str, int]] = []
        self._next_point_id = 1
        self._next_region_id = 1
        self._pan_last: Optional[QPointF] = None
        self._draft_region: Optional[Tuple[str, Tuple[int, int], Tuple[int, int]]] = None

    @property
    def show_extrema(self) -> bool:
        return self._show_extrema

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def point_markers(self) -> Sequence[PointMarker]:
        return tuple(self._point_markers)

    @property
    def regions(self) -> Sequence[RegionOfInterest]:
        return tuple(self._regions)

    def set_show_extrema(self, show: bool) -> None:
        self._show_extrema = bool(show)
        self.update()

    def set_interaction_mode(self, mode: str) -> None:
        if mode not in self._VALID_MODES:
            raise ValueError(f"Unknown canvas interaction mode: {mode}")
        self._interaction_mode = mode
        self._draft_region = None
        self._pan_last = None

    def set_measurement_editing_enabled(self, enabled: bool) -> None:
        self._measurement_editing_enabled = bool(enabled)

    def set_frame(self, frame: ThermalFrame, rgb: np.ndarray) -> None:
        previous_shape = self._frame.shape if self._frame is not None else None
        contiguous = np.ascontiguousarray(rgb, dtype=np.uint8)
        image = QImage(
            contiguous.data,
            frame.width,
            frame.height,
            int(contiguous.strides[0]),
            QImage.Format.Format_RGB888,
        )
        self._image = image.copy()
        self._frame = frame
        stats = frame.statistics()
        self._minimum_xy = stats.minimum_xy
        self._maximum_xy = stats.maximum_xy
        if previous_shape != frame.shape:
            self.reset_view()
            if previous_shape is not None:
                self.clear_measurements()
        self.update()

    def add_point_marker(self, x: int, y: int) -> PointMarker:
        self._validate_pixel(x, y)
        marker = PointMarker(self._next_point_id, x, y)
        self._next_point_id += 1
        self._point_markers.append(marker)
        self._history.append(("point", marker.identifier))
        self.measurements_changed.emit()
        self.update()
        return marker

    def add_region(
        self, kind: str, x0: int, y0: int, x1: int, y1: int
    ) -> RegionOfInterest:
        self._validate_pixel(x0, y0)
        self._validate_pixel(x1, y1)
        region = RegionOfInterest(self._next_region_id, kind, x0, y0, x1, y1)
        self._next_region_id += 1
        self._regions.append(region)
        self._history.append(("region", region.identifier))
        self.measurements_changed.emit()
        self.update()
        return region

    def set_measurements(
        self,
        point_markers: Sequence[PointMarker],
        regions: Sequence[RegionOfInterest],
    ) -> None:
        self._point_markers = list(point_markers)
        self._regions = list(regions)
        self._history = [
            *[("point", marker.identifier) for marker in self._point_markers],
            *[("region", region.identifier) for region in self._regions],
        ]
        self._next_point_id = (
            max((m.identifier for m in self._point_markers), default=0) + 1
        )
        self._next_region_id = (
            max((r.identifier for r in self._regions), default=0) + 1
        )
        self.measurements_changed.emit()
        self.update()

    def undo_last_measurement(self) -> None:
        if not self._history:
            return
        kind, identifier = self._history.pop()
        if kind == "point":
            self._point_markers = [m for m in self._point_markers if m.identifier != identifier]
        else:
            self._regions = [r for r in self._regions if r.identifier != identifier]
        self.measurements_changed.emit()
        self.update()

    def clear_measurements(self) -> None:
        if not self._point_markers and not self._regions:
            return
        self._point_markers.clear()
        self._regions.clear()
        self._history.clear()
        self._next_point_id = 1
        self._next_region_id = 1
        self.measurements_changed.emit()
        self.update()

    def zoom_in(self) -> None:
        self._set_zoom(self._zoom * 1.25)

    def zoom_out(self) -> None:
        self._set_zoom(self._zoom / 1.25)

    def reset_view(self) -> None:
        self._zoom = 1.0
        if self._frame is not None:
            self._view_center = QPointF(
                self._frame.width / 2.0, self._frame.height / 2.0
            )
        self.zoom_changed.emit(self._zoom)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#12151a"))
        if self._image is None or self._frame is None:
            painter.setPen(QColor("#aab2bf"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for a frame…"
            )
            return

        image_ratio = self._frame.width / self._frame.height
        widget_ratio = self.width() / max(1, self.height())
        if widget_ratio > image_ratio:
            height = float(self.height())
            width = height * image_ratio
        else:
            width = float(self.width())
            height = width / image_ratio
        left = (self.width() - width) / 2.0
        top = (self.height() - height) / 2.0
        self._display_rect = QRectF(left, top, width, height)

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(self._display_rect, self._image, self._source_rect())
        if self._show_extrema:
            self._draw_marker(painter, self._minimum_xy, QColor("#4dc3ff"), "MIN")
            self._draw_marker(painter, self._maximum_xy, QColor("#ffdb4d"), "MAX")
        for marker in self._point_markers:
            self._draw_marker(
                painter,
                (marker.x, marker.y),
                QColor("#69ff91"),
                f"P{marker.identifier}",
            )
        for region in self._regions:
            self._draw_region(painter, region)
        if self._draft_region is not None:
            kind, start, end = self._draft_region
            self._draw_region(
                painter, RegionOfInterest(0, kind, *start, *end), draft=True
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() in {Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton} or (
            event.button() == Qt.MouseButton.LeftButton and self._interaction_mode == "pan"
        ):
            if self._display_rect.contains(event.position()):
                self._pan_last = event.position()
            return
        if (
            event.button() != Qt.MouseButton.LeftButton
            or not self._measurement_editing_enabled
        ):
            return
        pixel = self.widget_to_pixel(event.position())
        if pixel is None:
            return
        if self._interaction_mode == "point":
            self.add_point_marker(*pixel)
        elif self._interaction_mode in {"rectangle", "circle"}:
            self._draft_region = (self._interaction_mode, pixel, pixel)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._pan_last is not None:
            delta = event.position() - self._pan_last
            self._pan_last = event.position()
            self._pan_by_widget_delta(delta)
        elif self._draft_region is not None:
            pixel = self.widget_to_pixel(event.position())
            if pixel is not None:
                kind, start, _ = self._draft_region
                self._draft_region = (kind, start, pixel)
                self.update()

        pixel = self.widget_to_pixel(event.position())
        if pixel is None or self._frame is None:
            self.hover_left.emit()
            return
        x, y = pixel
        self.pixel_hovered.emit(
            x,
            y,
            self._frame.raw_at(x, y),
            self._frame.temperature_at_celsius(x, y),
        )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._pan_last is not None:
            self._pan_last = None
            return
        if event.button() == Qt.MouseButton.LeftButton and self._draft_region is not None:
            kind, start, end = self._draft_region
            self._draft_region = None
            self.add_region(kind, *start, *end)

    def wheelEvent(self, event: QWheelEvent) -> None:
        steps = event.angleDelta().y() / 120.0
        if steps:
            self._set_zoom(self._zoom * (1.25**steps), event.position())
            event.accept()

    def leaveEvent(self, event: object) -> None:
        del event
        self.hover_left.emit()

    def widget_to_pixel(self, point: QPointF) -> Optional[Tuple[int, int]]:
        source = self._widget_to_source(point)
        if source is None or self._frame is None:
            return None
        x = min(self._frame.width - 1, max(0, int(source.x())))
        y = min(self._frame.height - 1, max(0, int(source.y())))
        return x, y

    def _widget_to_source(self, point: QPointF) -> Optional[QPointF]:
        if self._frame is None or not self._display_rect.contains(point):
            return None
        view = self._source_rect()
        relative_x = (point.x() - self._display_rect.left()) / self._display_rect.width()
        relative_y = (point.y() - self._display_rect.top()) / self._display_rect.height()
        return QPointF(
            view.left() + relative_x * view.width(),
            view.top() + relative_y * view.height(),
        )

    def _pixel_to_widget(self, x: float, y: float) -> QPointF:
        view = self._source_rect()
        return QPointF(
            self._display_rect.left()
            + (x - view.left()) * self._display_rect.width()
            / view.width(),
            self._display_rect.top()
            + (y - view.top()) * self._display_rect.height()
            / view.height(),
        )

    def _source_rect(self) -> QRectF:
        if self._frame is None:
            return QRectF()
        width = self._frame.width / self._zoom
        height = self._frame.height / self._zoom
        return QRectF(
            self._view_center.x() - width / 2.0,
            self._view_center.y() - height / 2.0,
            width,
            height,
        )

    def _set_zoom(self, zoom: float, anchor: Optional[QPointF] = None) -> None:
        if self._frame is None:
            return
        new_zoom = min(16.0, max(1.0, float(zoom)))
        if abs(new_zoom - self._zoom) < 1e-9:
            return
        anchor_source = self._widget_to_source(anchor) if anchor is not None else None
        relative_x = relative_y = 0.5
        if anchor is not None and self._display_rect.contains(anchor):
            relative_x = (
                anchor.x() - self._display_rect.left()
            ) / self._display_rect.width()
            relative_y = (
                anchor.y() - self._display_rect.top()
            ) / self._display_rect.height()
        self._zoom = new_zoom
        if anchor_source is not None:
            new_width = self._frame.width / self._zoom
            new_height = self._frame.height / self._zoom
            self._view_center = QPointF(
                anchor_source.x() - (relative_x - 0.5) * new_width,
                anchor_source.y() - (relative_y - 0.5) * new_height,
            )
        self._clamp_view_center()
        self.zoom_changed.emit(self._zoom)
        self.update()

    def _pan_by_widget_delta(self, delta: QPointF) -> None:
        if self._frame is None or self._zoom <= 1.0:
            return
        view = self._source_rect()
        self._view_center = QPointF(
            self._view_center.x() - delta.x() * view.width() / self._display_rect.width(),
            self._view_center.y() - delta.y() * view.height() / self._display_rect.height(),
        )
        self._clamp_view_center()
        self.update()

    def _clamp_view_center(self) -> None:
        if self._frame is None:
            return
        half_width = self._frame.width / self._zoom / 2.0
        half_height = self._frame.height / self._zoom / 2.0
        self._view_center = QPointF(
            min(
                self._frame.width - half_width,
                max(half_width, self._view_center.x()),
            ),
            min(
                self._frame.height - half_height,
                max(half_height, self._view_center.y()),
            ),
        )

    def _draw_marker(
        self,
        painter: QPainter,
        pixel: Optional[Tuple[int, int]],
        color: QColor,
        label: str,
    ) -> None:
        if pixel is None or self._frame is None:
            return
        point = self._pixel_to_widget(pixel[0] + 0.5, pixel[1] + 0.5)
        if not self._display_rect.contains(point):
            return
        painter.setPen(QPen(color, 2.0))
        painter.drawLine(
            QPointF(point.x() - 8, point.y()), QPointF(point.x() + 8, point.y())
        )
        painter.drawLine(
            QPointF(point.x(), point.y() - 8), QPointF(point.x(), point.y() + 8)
        )
        painter.drawText(QPointF(point.x() + 10, point.y() - 5), label)

    def _draw_region(
        self, painter: QPainter, region: RegionOfInterest, draft: bool = False
    ) -> None:
        left, top, right, bottom = region.bounds
        rectangle = QRectF(
            self._pixel_to_widget(left, top), self._pixel_to_widget(right + 1, bottom + 1)
        ).normalized()
        pen = QPen(QColor("#69ff91"), 2.0)
        if draft:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        if region.kind == "circle":
            painter.drawEllipse(rectangle)
            prefix = "C"
        else:
            painter.drawRect(rectangle)
            prefix = "R"
        if not draft:
            painter.drawText(
                rectangle.topLeft() + QPointF(4, 14), f"{prefix}{region.identifier}"
            )

    def _validate_pixel(self, x: int, y: int) -> None:
        if self._frame is None:
            raise RuntimeError("No frame is loaded")
        if not (0 <= x < self._frame.width and 0 <= y < self._frame.height):
            raise IndexError((x, y))
