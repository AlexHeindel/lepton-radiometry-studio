from __future__ import annotations

# VoSPI/CCI implementation adapted from TRACES-Research/lepton-thermal (MIT).
# See THIRD_PARTY_NOTICES.md.

import errno
import os
import platform
import struct
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, Tuple

import numpy as np

from lepton_radiometry_studio.domain import ThermalFrame
from lepton_radiometry_studio.sources.base import FrameSource


PACKET_SIZE = 164
PACKETS_PER_SEGMENT = 60
SEGMENTS_PER_FRAME = 4
ROWS_PER_SEGMENT = 30
PIXELS_PER_PACKET = 80
FRAME_WIDTH = 160
FRAME_HEIGHT = 120
SEGMENT_BYTES = PACKETS_PER_SEGMENT * PACKET_SIZE
VOSPI_RESYNC_SECONDS = 0.185
SPIDEV_MESSAGE_PACKET_LIMIT = 24

_SPI_IOC_MAGIC = ord("k")
_SPI_TRANSFER = struct.Struct("=QQIIHBBI")
_IOC_WRITE = 1
_IOC_TYPESHIFT = 8
_IOC_SIZESHIFT = 16
_IOC_DIRSHIFT = 30

LEPTON_I2C_ADDRESS = 0x2A
CCI_REG_STATUS = 0x0002
CCI_REG_COMMAND = 0x0004
CCI_REG_DATA_LENGTH = 0x0006
CCI_REG_DATA_0 = 0x0008

SYS_AUX_TEMP_KELVIN = 0x0210
SYS_FPA_TEMP_KELVIN = 0x0214
SYS_FFC_RUN = 0x0242
RAD_TLINEAR_ENABLE_GET = 0x4EC0
RAD_TLINEAR_ENABLE_SET = 0x4EC1
RAD_TLINEAR_RES_GET = 0x4EC4
RAD_TLINEAR_RES_SET = 0x4EC5


class LeptonUnavailableError(RuntimeError):
    """The Pi interfaces, dependencies, or Lepton hardware are unavailable."""


class LeptonFrameTimeout(RuntimeError):
    """A complete four-segment Lepton 3 frame was not received in time."""


def _spi_ioc_message(transfer_count: int) -> int:
    """Return Linux's SPI_IOC_MESSAGE request for transfer_count entries."""
    size = _SPI_TRANSFER.size * transfer_count
    return (
        (_IOC_WRITE << _IOC_DIRSHIFT)
        | (_SPI_IOC_MAGIC << _IOC_TYPESHIFT)
        | (size << _IOC_SIZESHIFT)
    )


class LeptonSPI:
    """Read and assemble Lepton 3.x VoSPI packets from Linux spidev."""

    def __init__(
        self,
        bus: int = 0,
        device: int = 0,
        speed_hz: int = 20_000_000,
        mode: int = 3,
        spi_factory: Optional[Callable[[], Any]] = None,
        ioctl_func: Optional[Callable[..., int]] = None,
    ) -> None:
        if spi_factory is None:
            try:
                import spidev
            except ImportError as exc:
                raise LeptonUnavailableError(
                    "Python package 'spidev' is not installed; install the Pi extras."
                ) from exc
            spi_factory = spidev.SpiDev
        self.bus = int(bus)
        self.device = int(device)
        self.speed_hz = int(speed_hz)
        self.mode = int(mode)
        self._needs_resync = True
        self._ioctl_func = ioctl_func
        self._message_packet_limit = SPIDEV_MESSAGE_PACKET_LIMIT
        self._spi = spi_factory()
        try:
            self._open()
        except Exception as exc:
            raise LeptonUnavailableError(
                f"Could not open /dev/spidev{self.bus}.{self.device}: {exc}"
            ) from exc

    def _open(self) -> None:
        self._spi.open(self.bus, self.device)
        self._spi.mode = self.mode
        self._spi.max_speed_hz = self.speed_hz

    def _read_packet_batch(self, count: int) -> list[bytes]:
        """Clock count packets with CS toggled after every packet."""
        fileno = getattr(self._spi, "fileno", None)
        if not callable(fileno):
            return [bytes(self._spi.readbytes(PACKET_SIZE)) for _ in range(count)]

        if self._ioctl_func is None:
            from fcntl import ioctl

            self._ioctl_func = ioctl

        tx = np.zeros((count, PACKET_SIZE), dtype=np.uint8)
        rx = np.empty((count, PACKET_SIZE), dtype=np.uint8)
        transfers = bytearray(_SPI_TRANSFER.size * count)
        for index in range(count):
            _SPI_TRANSFER.pack_into(
                transfers,
                index * _SPI_TRANSFER.size,
                tx.ctypes.data + index * PACKET_SIZE,
                rx.ctypes.data + index * PACKET_SIZE,
                PACKET_SIZE,
                self.speed_hz,
                0,
                8,
                1,
                0,
            )

        try:
            transferred = self._ioctl_func(
                fileno(), _spi_ioc_message(count), transfers, True
            )
        except OSError as exc:
            if exc.errno != errno.EMSGSIZE or count <= 1:
                raise
            # Controller drivers can impose a smaller message limit than
            # spidev's buffer. Split the request and retain the working limit.
            first_count = count // 2
            self._message_packet_limit = min(
                self._message_packet_limit, first_count
            )
            return self._read_packet_batch(first_count) + self._read_packet_batch(
                count - first_count
            )
        expected = count * PACKET_SIZE
        if transferred != expected:
            raise OSError(
                f"SPI packet batch transferred {transferred} of {expected} bytes"
            )
        return [row.tobytes() for row in rx]

    def grab_frame(self, timeout: float = 2.5) -> np.ndarray:
        deadline = time.monotonic() + timeout
        segment_data: list[Optional[bytes]] = [None] * SEGMENTS_PER_FRAME
        completed = 0
        expected_packet = -1
        current_segment = -1
        segment_buffer = bytearray(SEGMENT_BYTES)
        pending_packets: deque[bytes] = deque()

        while completed < SEGMENTS_PER_FRAME and time.monotonic() < deadline:
            if self._needs_resync:
                # VoSPI resets its packet state after CS has remained deasserted
                # for at least 185 ms. No SPI calls during this delay keeps CS high.
                time.sleep(VOSPI_RESYNC_SECONDS)
                segment_data = [None] * SEGMENTS_PER_FRAME
                completed = 0
                expected_packet = -1
                current_segment = -1
                pending_packets.clear()
                self._needs_resync = False

            if not pending_packets:
                if expected_packet > 0:
                    count = min(
                        self._message_packet_limit,
                        PACKETS_PER_SEGMENT - expected_packet,
                    )
                    pending_packets.extend(self._read_packet_batch(count))
                else:
                    pending_packets.append(bytes(self._spi.readbytes(PACKET_SIZE)))
            packet = pending_packets.popleft()
            if len(packet) != PACKET_SIZE:
                self._needs_resync = True
                pending_packets.clear()
                continue

            if (packet[0] & 0x0F) == 0x0F:
                if expected_packet != -1:
                    self._needs_resync = True
                    expected_packet = -1
                    current_segment = -1
                    pending_packets.clear()
                continue

            packet_number = ((packet[0] & 0x0F) << 8) | packet[1]
            if expected_packet == -1:
                if packet_number != 0:
                    continue
                expected_packet = 0
            if packet_number != expected_packet:
                self._needs_resync = True
                expected_packet = -1
                current_segment = -1
                pending_packets.clear()
                continue

            packet_offset = packet_number * PACKET_SIZE
            segment_buffer[packet_offset : packet_offset + PACKET_SIZE] = packet
            if packet_number == 20:
                current_segment = (packet[0] >> 4) & 0x07

            expected_packet += 1
            if packet_number != PACKETS_PER_SEGMENT - 1:
                continue

            if current_segment == 1:
                segment_data = [None] * SEGMENTS_PER_FRAME
                completed = 0
            if current_segment == completed + 1:
                segment_data[current_segment - 1] = bytes(segment_buffer)
                completed += 1
            elif completed:
                segment_data = [None] * SEGMENTS_PER_FRAME
                completed = 0
            expected_packet = -1
            current_segment = -1

        if completed != SEGMENTS_PER_FRAME:
            self._needs_resync = True
            raise LeptonFrameTimeout(
                f"Timed out receiving a complete Lepton frame "
                f"({completed}/{SEGMENTS_PER_FRAME} segments). "
                "Check SPI wiring and chip select."
            )
        return assemble_frame(segment_data)

    def close(self) -> None:
        self._spi.close()


def assemble_frame(segment_data: Sequence[Optional[bytes]]) -> np.ndarray:
    """Assemble four validated VoSPI segments into one 160 x 120 frame."""
    if len(segment_data) != SEGMENTS_PER_FRAME or any(
        segment is None or len(segment) != SEGMENT_BYTES for segment in segment_data
    ):
        raise ValueError("Four complete VoSPI segments are required")

    frame = np.empty((FRAME_HEIGHT, FRAME_WIDTH), dtype=np.uint16)
    for segment_index, segment in enumerate(segment_data):
        assert segment is not None
        for packet_number in range(PACKETS_PER_SEGMENT):
            offset = packet_number * PACKET_SIZE
            pixels = np.frombuffer(
                segment[offset + 4 : offset + PACKET_SIZE], dtype=">u2"
            )
            row = segment_index * ROWS_PER_SEGMENT + packet_number // 2
            column = (packet_number % 2) * PIXELS_PER_PACKET
            frame[row, column : column + PIXELS_PER_PACKET] = pixels
    return frame


class LeptonCCI:
    """Lepton command-and-control interface over Linux I2C."""

    def __init__(
        self,
        bus_number: int = 1,
        bus_factory: Optional[Callable[[int], Any]] = None,
    ) -> None:
        try:
            from smbus2 import SMBus, i2c_msg
        except ImportError as exc:
            raise LeptonUnavailableError(
                "Python package 'smbus2' is not installed; install the Pi extras."
            ) from exc
        self._i2c_msg = i2c_msg
        factory = SMBus if bus_factory is None else bus_factory
        try:
            self._bus = factory(bus_number)
        except Exception as exc:
            raise LeptonUnavailableError(
                f"Could not open /dev/i2c-{bus_number}: {exc}"
            ) from exc

    def _write_register(self, register: int, value: int) -> None:
        message = self._i2c_msg.write(
            LEPTON_I2C_ADDRESS, struct.pack(">HH", register, value)
        )
        self._bus.i2c_rdwr(message)

    def _read_register(self, register: int) -> int:
        write = self._i2c_msg.write(LEPTON_I2C_ADDRESS, struct.pack(">H", register))
        read = self._i2c_msg.read(LEPTON_I2C_ADDRESS, 2)
        self._bus.i2c_rdwr(write, read)
        return struct.unpack(">H", bytes(read))[0]

    def wait_ready(self, timeout: float = 1.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self._read_register(CCI_REG_STATUS)
            if not status & 0x01:
                error = (status >> 8) & 0xFF
                if error:
                    raise RuntimeError(f"Lepton CCI error {error:#x}")
                return
            time.sleep(0.005)
        raise TimeoutError("Lepton I2C command timed out")

    def _command(
        self, command: int, words: Optional[Sequence[int]] = None
    ) -> list[int]:
        self.wait_ready()
        if words is not None:
            for index, word in enumerate(words):
                self._write_register(CCI_REG_DATA_0 + index * 2, int(word))
            self._write_register(CCI_REG_DATA_LENGTH, len(words))
        self._write_register(CCI_REG_COMMAND, command)
        self.wait_ready()
        if command & 0x03:
            return []
        length = self._read_register(CCI_REG_DATA_LENGTH)
        return [
            self._read_register(CCI_REG_DATA_0 + index * 2)
            for index in range(length)
        ]

    def radiometry(self) -> Tuple[bool, float]:
        enabled = self._command(RAD_TLINEAR_ENABLE_GET)
        resolution = self._command(RAD_TLINEAR_RES_GET)
        scale = 0.01 if resolution and resolution[0] == 1 else 0.1
        return bool(enabled and enabled[0]), scale

    def enable_radiometry(self) -> None:
        self._command(RAD_TLINEAR_ENABLE_SET, [1])
        self._command(RAD_TLINEAR_RES_SET, [1])

    def fpa_temperature_c(self) -> float:
        return self._command(SYS_FPA_TEMP_KELVIN)[0] / 100.0 - 273.15

    def aux_temperature_c(self) -> float:
        return self._command(SYS_AUX_TEMP_KELVIN)[0] / 100.0 - 273.15

    def run_ffc(self) -> None:
        self._command(SYS_FFC_RUN)

    def close(self) -> None:
        self._bus.close()


class LeptonSource(FrameSource):
    """Radiometric FLIR Lepton 3.5 source for a Pi GPIO breakout board."""

    def __init__(
        self,
        spi_bus: int = 0,
        spi_device: int = 0,
        i2c_bus: int = 1,
        spi_factory: Optional[Callable[[], Any]] = None,
        cci_factory: Callable[[int], LeptonCCI] = LeptonCCI,
    ) -> None:
        self.spi_bus = int(spi_bus)
        self.spi_device = int(spi_device)
        self.i2c_bus = int(i2c_bus)
        self._spi_factory = spi_factory
        self._cci_factory = cci_factory
        self._spi: Optional[LeptonSPI] = None
        self._cci: Optional[LeptonCCI] = None
        self._prefetched_frame: Optional[ThermalFrame] = None
        self._frame_index = 0
        self._temperature_scale = 0.01
        self._sensor_telemetry: dict[str, float] = {}

    @property
    def name(self) -> str:
        return f"FLIR Lepton 3.5 (SPI {self.spi_bus}.{self.spi_device})"

    def start(self) -> None:
        if self._spi is not None:
            return
        try:
            self._cci = self._cci_factory(self.i2c_bus)
            self._cci.wait_ready()
            enabled, resolution = self._cci.radiometry()
            if not enabled or resolution != 0.01:
                self._cci.enable_radiometry()
                enabled, resolution = self._cci.radiometry()
            if not enabled:
                raise LeptonUnavailableError(
                    "The Lepton did not enable radiometric output"
                )
            self._temperature_scale = resolution
            self._read_sensor_telemetry()
            self._spi = LeptonSPI(
                self.spi_bus,
                self.spi_device,
                spi_factory=self._spi_factory,
            )
        except Exception:
            self.stop()
            raise

    def prepare(self, timeout: float = 2.5) -> None:
        self.start()
        self._prefetched_frame = self._capture_frame(timeout)

    def next_frame(self) -> ThermalFrame:
        if self._prefetched_frame is not None:
            frame = self._prefetched_frame
            self._prefetched_frame = None
            return frame
        if self._spi is None:
            raise RuntimeError("Lepton source has not been started")
        return self._capture_frame(2.5)

    def _capture_frame(self, timeout: float) -> ThermalFrame:
        assert self._spi is not None
        started = time.monotonic()
        raw = self._spi.grab_frame(timeout)
        if self._frame_index and self._frame_index % 30 == 0:
            self._read_sensor_telemetry()
        frame = ThermalFrame(
            raw=raw,
            timestamp_ns=time.time_ns(),
            temperature_scale=self._temperature_scale,
            telemetry={
                "source": "flir_lepton_3_5",
                "frame_index": self._frame_index,
                "capture_duration_ms": (time.monotonic() - started) * 1000.0,
                **self._sensor_telemetry,
            },
            camera_settings={
                "radiometric": True,
                "tlinear_resolution_k": self._temperature_scale,
                "spi_bus": self.spi_bus,
                "spi_device": self.spi_device,
                "spi_speed_hz": 20_000_000,
                "spi_mode": 3,
                "i2c_bus": self.i2c_bus,
                "i2c_address": LEPTON_I2C_ADDRESS,
            },
        )
        self._frame_index += 1
        return frame

    def _read_sensor_telemetry(self) -> None:
        if self._cci is None:
            return
        try:
            self._sensor_telemetry = {
                "fpa_temperature_c": self._cci.fpa_temperature_c(),
                "aux_temperature_c": self._cci.aux_temperature_c(),
            }
        except Exception:
            # Scene capture remains useful if an optional telemetry read fails.
            self._sensor_telemetry = {}

    def run_ffc(self) -> None:
        if self._cci is None:
            raise RuntimeError("Lepton source has not been started")
        self._cci.run_ffc()

    def stop(self) -> None:
        if self._spi is not None:
            self._spi.close()
            self._spi = None
        if self._cci is not None:
            self._cci.close()
            self._cci = None
        self._prefetched_frame = None

    @classmethod
    def autodetect(cls) -> "LeptonSource":
        if platform.system() != "Linux":
            raise LeptonUnavailableError(
                "Live Lepton capture is available on Linux/Raspberry Pi"
            )
        if not Path("/dev/i2c-1").exists():
            raise LeptonUnavailableError("/dev/i2c-1 is missing; enable I2C and reboot")

        candidates = _spi_candidates()
        errors: list[str] = []
        for bus, device in candidates:
            path = Path(f"/dev/spidev{bus}.{device}")
            if not path.exists():
                errors.append(f"{path} is missing")
                continue
            source = cls(spi_bus=bus, spi_device=device)
            try:
                source.prepare()
                return source
            except Exception as exc:
                source.stop()
                errors.append(f"SPI {bus}.{device}: {exc}")
        detail = "; ".join(errors) if errors else "no SPI devices were found"
        raise LeptonUnavailableError(detail)


def _spi_candidates() -> list[Tuple[int, int]]:
    configured = os.environ.get("LEPTON_SPI_DEVICE", "").strip()
    if configured:
        try:
            bus, device = configured.split(".", 1)
            return [(int(bus), int(device))]
        except ValueError as exc:
            raise LeptonUnavailableError(
                "LEPTON_SPI_DEVICE must look like '0.0' or '0.1'"
            ) from exc
    # SparkFun's historical guide used CE1 (0.1), while FLIR's newer Pi guide
    # uses CE0 (0.0). Try both so either hookup can be detected.
    return [(0, 0), (0, 1)]
