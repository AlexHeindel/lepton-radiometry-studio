from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QCloseEvent, QImage, QKeyEvent, QPaintEvent, QPainter
from PySide6.QtWidgets import QMainWindow, QWidget

from lepton_radiometry_studio.processing.palettes import PALETTES, render_frame
from lepton_radiometry_studio.sources.base import FrameSource
from lepton_radiometry_studio.sources.lepton import LeptonFrameTimeout, LeptonSource
from lepton_radiometry_studio.sources.synthetic import SyntheticSource

FRAME_TIMEOUT_LIMIT = 5


class FeedCanvas(QWidget):
    """A paint-only RGB canvas with no inspection or interaction tools."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(320, 240)
        self._buffer: Optional[np.ndarray] = None
        self._image: Optional[QImage] = None
        self._message = "Connecting to camera…"

    @property
    def has_image(self) -> bool:
        return self._image is not None

    def set_frame(self, rgb: np.ndarray) -> None:
        buffer = np.ascontiguousarray(rgb, dtype=np.uint8)
        height, width, _channels = buffer.shape
        self._buffer = buffer
        self._image = QImage(
            buffer.data,
            width,
            height,
            int(buffer.strides[0]),
            QImage.Format.Format_RGB888,
        )
        self.update()

    def show_message(self, message: str, clear: bool = False) -> None:
        self._message = message
        if clear:
            self._buffer = None
            self._image = None
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        if self._image is None:
            painter.setPen(QColor("#aab2bf"))
            painter.drawText(
                self.rect().adjusted(30, 30, -30, -30),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self._message,
            )
            return

        image_ratio = self._image.width() / self._image.height()
        widget_ratio = self.width() / max(1, self.height())
        if widget_ratio > image_ratio:
            height = float(self.height())
            width = height * image_ratio
        else:
            width = float(self.width())
            height = width / image_ratio
        target = QRectF(
            (self.width() - width) / 2.0,
            (self.height() - height) / 2.0,
            width,
            height,
        )
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(target, self._image)


class FeedWindow(QMainWindow):
    """Live feed window without menus, status bars, controls, or analysis."""

    def __init__(
        self,
        palette: str = "Iron",
        source_kind: str = "camera",
        auto_connect: bool = True,
    ) -> None:
        super().__init__()
        if palette not in PALETTES:
            raise ValueError(f"Unknown palette: {palette}")
        if source_kind not in {"camera", "synthetic"}:
            raise ValueError(f"Unknown source: {source_kind}")
        self.setWindowTitle("Lepton Viewer")
        self.resize(640, 480)
        self.canvas = FeedCanvas()
        self.setCentralWidget(self.canvas)

        self.palette = palette
        self.source_kind = source_kind
        self._source: Optional[FrameSource] = None
        self._closed = False
        self._timeout_count = 0
        self._frame_timer = QTimer(self)
        self._frame_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._frame_timer.timeout.connect(self._acquire_frame)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.setInterval(2000)
        self._reconnect_timer.timeout.connect(self._connect_source)
        if auto_connect:
            QTimer.singleShot(0, self._connect_source)

    def _connect_source(self) -> None:
        if self._closed:
            return
        self._frame_timer.stop()
        self._stop_source()
        self.canvas.show_message("Connecting to camera…", clear=True)
        try:
            source: FrameSource
            if self.source_kind == "synthetic":
                source = SyntheticSource()
                source.start()
            else:
                source = LeptonSource.autodetect()
        except Exception as exc:
            self.canvas.show_message(
                f"Camera unavailable\n\n{exc}\n\nRetrying…", clear=True
            )
            self._reconnect_timer.start()
            return
        self._source = source
        self._timeout_count = 0
        self._frame_timer.start(max(1, round(1000.0 / source.nominal_fps)))
        self._acquire_frame()

    def _acquire_frame(self) -> None:
        if self._source is None:
            return
        try:
            frame = self._source.next_frame()
        except LeptonFrameTimeout:
            self._timeout_count += 1
            if self._timeout_count < FRAME_TIMEOUT_LIMIT:
                return
            self._schedule_reconnect()
            return
        except Exception:
            self._schedule_reconnect()
            return
        self._timeout_count = 0
        self.canvas.set_frame(render_frame(frame, palette=self.palette))

    def _schedule_reconnect(self) -> None:
        self._frame_timer.stop()
        self._stop_source()
        self.canvas.show_message("Camera connection lost\n\nRetrying…", clear=True)
        self._reconnect_timer.start()

    def _stop_source(self) -> None:
        source = self._source
        self._source = None
        if source is not None:
            try:
                source.stop()
            except Exception:
                pass

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._closed = True
        self._frame_timer.stop()
        self._reconnect_timer.stop()
        self._stop_source()
        event.accept()
