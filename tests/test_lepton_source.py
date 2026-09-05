from __future__ import annotations

import numpy as np
import pytest

from lepton_radiometry_studio.sources.lepton import (
    PACKET_SIZE,
    PACKETS_PER_SEGMENT,
    SEGMENT_BYTES,
    LeptonSPI,
    LeptonSource,
    assemble_frame,
)


def _segments() -> list[bytes]:
    segments = []
    for segment_number in range(1, 5):
        data = bytearray(SEGMENT_BYTES)
        for packet_number in range(PACKETS_PER_SEGMENT):
            offset = packet_number * PACKET_SIZE
            data[offset] = segment_number << 4 if packet_number == 20 else 0
            data[offset + 1] = packet_number
            row = (segment_number - 1) * 30 + packet_number // 2
            column = (packet_number % 2) * 80
            values = (
                np.arange(column, column + 80, dtype=np.uint16) + row * 200
            ).astype(">u2")
            data[offset + 4 : offset + PACKET_SIZE] = values.tobytes()
        segments.append(bytes(data))
    return segments


def test_assemble_frame_maps_four_segments_and_packet_halves() -> None:
    frame = assemble_frame(_segments())

    assert frame.shape == (120, 160)
    assert frame.dtype == np.uint16
    assert frame[0, 0] == 0
    assert frame[0, 159] == 159
    assert frame[30, 0] == 6000
    assert frame[119, 159] == 23959


def test_assemble_frame_rejects_incomplete_segments() -> None:
    with pytest.raises(ValueError, match="Four complete"):
        assemble_frame(_segments()[:3])


def test_spi_reader_accepts_a_complete_vospi_frame() -> None:
    stream = b"".join(_segments())

    class FakeSPI:
        def __init__(self) -> None:
            self.offset = 0
            self.mode = None
            self.max_speed_hz = None

        def open(self, bus: int, device: int) -> None:
            assert (bus, device) == (0, 1)

        def readbytes(self, count: int) -> list[int]:
            result = stream[self.offset : self.offset + count]
            self.offset += count
            return list(result)

        def close(self) -> None:
            pass

    reader = LeptonSPI(bus=0, device=1, spi_factory=FakeSPI)
    frame = reader.grab_frame(timeout=0.5)

    assert frame[119, 159] == 23959
    assert reader._spi.mode == 3
    assert reader._spi.max_speed_hz == 20_000_000


def test_lepton_source_emits_radiometric_frame_with_hardware_metadata() -> None:
    stream = b"".join(_segments())

    class FakeSPI:
        def __init__(self) -> None:
            self.offset = 0

        def open(self, _bus: int, _device: int) -> None:
            pass

        def readbytes(self, count: int) -> list[int]:
            result = stream[self.offset : self.offset + count]
            self.offset += count
            return list(result)

        def close(self) -> None:
            pass

    class FakeCCI:
        def wait_ready(self) -> None:
            pass

        def radiometry(self) -> tuple[bool, float]:
            return True, 0.01

        def enable_radiometry(self) -> None:
            raise AssertionError("Radiometry is already enabled")

        def fpa_temperature_c(self) -> float:
            return 31.25

        def aux_temperature_c(self) -> float:
            return 30.75

        def close(self) -> None:
            pass

    source = LeptonSource(
        spi_device=1,
        spi_factory=FakeSPI,
        cci_factory=lambda _bus: FakeCCI(),
    )
    source.prepare(timeout=0.5)
    frame = source.next_frame()
    source.stop()

    assert frame.shape == (120, 160)
    assert frame.temperature_scale == 0.01
    assert frame.camera_settings["spi_device"] == 1
    assert frame.camera_settings["radiometric"] is True
    assert frame.telemetry["source"] == "flir_lepton_3_5"
    assert frame.telemetry["fpa_temperature_c"] == 31.25
