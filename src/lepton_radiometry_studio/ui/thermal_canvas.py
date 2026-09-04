from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Signal, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from lepton_radiometry_studio.domain import ThermalFrame


class ThermalCanvas(QWidget):
    pixel_hovered = Signal(int, int, int, float)
    hover_left = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(480, 360)
        self._frame: Optional[ThermalFrame] = None
        self._image: Optional[QImage] = None
        self._display_rect = QRectF()
        self._minimum_xy: Optional[Tuple[int, int]] = None
        self._maximum_xy: Optional[Tuple[int, int]] = None

    def set_frame(self, frame: ThermalFrame, rgb: np.ndarray) -> None:
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
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#12151a"))
        if self._image is None or self._frame is None:
            painter.setPen(QColor("#aab2bf"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for a frame…")
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
        painter.drawImage(self._display_rect, self._image)
        self._draw_marker(painter, self._minimum_xy, QColor("#4dc3ff"), "MIN")
        self._draw_marker(painter, self._maximum_xy, QColor("#ffdb4d"), "MAX")

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pixel = self.widget_to_pixel(event.position())
        if pixel is None or self._frame is None:
            self.hover_left.emit()
            return
        x, y = pixel
        self.pixel_hovered.emit(
            x, y, self._frame.raw_at(x, y), self._frame.temperature_at_celsius(x, y)
        )

    def leaveEvent(self, event: object) -> None:
        del event
        self.hover_left.emit()

    def widget_to_pixel(self, point: QPointF) -> Optional[Tuple[int, int]]:
        if self._frame is None or not self._display_rect.contains(point):
            return None
        relative_x = (point.x() - self._display_rect.left()) / self._display_rect.width()
        relative_y = (point.y() - self._display_rect.top()) / self._display_rect.height()
        x = min(self._frame.width - 1, max(0, int(relative_x * self._frame.width)))
        y = min(self._frame.height - 1, max(0, int(relative_y * self._frame.height)))
        return x, y

    def _draw_marker(
        self,
        painter: QPainter,
        pixel: Optional[Tuple[int, int]],
        color: QColor,
        label: str,
    ) -> None:
        if pixel is None or self._frame is None:
            return
        x, y = pixel
        px = self._display_rect.left() + (x + 0.5) * self._display_rect.width() / self._frame.width
        py = self._display_rect.top() + (y + 0.5) * self._display_rect.height() / self._frame.height
        painter.setPen(QPen(color, 2.0))
        painter.drawLine(QPointF(px - 8, py), QPointF(px + 8, py))
        painter.drawLine(QPointF(px, py - 8), QPointF(px, py + 8))
        painter.drawText(QPointF(px + 10, py - 5), label)

