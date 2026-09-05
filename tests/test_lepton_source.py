from __future__ import annotations

import ctypes
import errno

import numpy as np
import pytest

from lepton_radiometry_studio.sources.lepton import (
    CCI_REG_COMMAND,
    OEM_REBOOT_RUN,
    PACKET_SIZE,
    PACKETS_PER_SEGMENT,
    SEGMENT_BYTES,
    SPIDEV_MESSAGE_PACKET_LIMIT,
    VOSPI_RESYNC_SECONDS,
    _SPI_TRANSFER,
    LeptonCCI,
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
            self.read_sizes: list[int] = []

        def open(self, bus: int, device: int) -> None:
            assert (bus, device) == (0, 1)

        def readbytes(self, count: int) -> list[int]:
            self.read_sizes.append(count)
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
    assert set(reader._spi.read_sizes) == {PACKET_SIZE}


def test_spi_reader_batches_packets_with_cs_change(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = b"".join(_segments())
    offset = 0
    transfer_counts: list[int] = []

    class FakeSPI:
        def open(self, _bus: int, _device: int) -> None:
            pass

        def fileno(self) -> int:
            return 7

        def readbytes(self, count: int) -> list[int]:
            nonlocal offset
            result = stream[offset : offset + count]
            offset += count
            return list(result)

        def close(self) -> None:
            pass

    def fake_ioctl(
        fd: int, _request: int, transfers: bytearray, mutate: bool
    ) -> int:
        nonlocal offset
        assert fd == 7
        assert mutate is True
        count = len(transfers) // _SPI_TRANSFER.size
        transfer_counts.append(count)
        for index in range(count):
            fields = _SPI_TRANSFER.unpack_from(
                transfers, index * _SPI_TRANSFER.size
            )
            _tx_address, rx_address, length, speed, delay, bits, cs_change, pad = (
                fields
            )
            assert length == PACKET_SIZE
            assert speed == 20_000_000
            assert delay == 0
            assert bits == 8
            assert cs_change == 1
            assert pad == 0
            packet = stream[offset : offset + PACKET_SIZE]
            ctypes.memmove(rx_address, packet, PACKET_SIZE)
            offset += PACKET_SIZE
        return count * PACKET_SIZE

    monkeypatch.setattr(
        "lepton_radiometry_studio.sources.lepton.time.sleep", lambda _delay: None
    )
    reader = LeptonSPI(spi_factory=FakeSPI, ioctl_func=fake_ioctl)

    frame = reader.grab_frame(timeout=0.5)

    assert frame[119, 159] == 23959
    assert transfer_counts == [
        SPIDEV_MESSAGE_PACKET_LIMIT,
        SPIDEV_MESSAGE_PACKET_LIMIT,
        SPIDEV_MESSAGE_PACKET_LIMIT,
        11,
    ] * 4


def test_spi_reader_adapts_to_a_smaller_controller_message_limit() -> None:
    attempts: list[int] = []

    class FakeSPI:
        def open(self, _bus: int, _device: int) -> None:
            pass

        def fileno(self) -> int:
            return 7

        def close(self) -> None:
            pass

    def limited_ioctl(
        _fd: int, _request: int, transfers: bytearray, _mutate: bool
    ) -> int:
        count = len(transfers) // _SPI_TRANSFER.size
        attempts.append(count)
        if count > 12:
            raise OSError(errno.EMSGSIZE, "Message too long")
        return count * PACKET_SIZE

    reader = LeptonSPI(spi_factory=FakeSPI, ioctl_func=limited_ioctl)

    packets = reader._read_packet_batch(24)

    assert len(packets) == 24
    assert attempts == [24, 12, 12]
    assert reader._message_packet_limit == 12


def test_spi_reader_resynchronizes_after_a_broken_packet_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    segments = _segments()
    stream = segments[0][:PACKET_SIZE] + segments[0][2 * PACKET_SIZE :]
    stream += b"".join(segments)
    sleeps: list[float] = []

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

    monkeypatch.setattr(
        "lepton_radiometry_studio.sources.lepton.time.sleep", sleeps.append
    )
    reader = LeptonSPI(spi_factory=FakeSPI)

    frame = reader.grab_frame(timeout=0.5)

    assert frame[119, 159] == 23959
    assert sleeps == [VOSPI_RESYNC_SECONDS, VOSPI_RESYNC_SECONDS]


def test_lepton_source_emits_radiometric_frame_with_hardware_metadata() -> None:
    stream = b"".join(_segments()) * 2

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
    next_frame = source.next_frame()
    source.stop()

    assert frame.shape == (120, 160)
    assert frame.temperature_scale == 0.01
    assert frame.camera_settings["spi_device"] == 1
    assert frame.camera_settings["radiometric"] is True
    assert frame.telemetry["source"] == "flir_lepton_3_5"
    assert frame.telemetry["fpa_temperature_c"] == 31.25
    assert next_frame.telemetry["frame_index"] == 1


def test_cci_reboot_issues_run_command_without_waiting_for_completion() -> None:
    writes: list[tuple[int, int]] = []
    cci = object.__new__(LeptonCCI)
    cci.wait_ready = lambda: None
    cci._write_register = lambda register, value: writes.append((register, value))

    cci.reboot()

    assert writes == [(CCI_REG_COMMAND, OEM_REBOOT_RUN)]
