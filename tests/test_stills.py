import json

import numpy as np
import pytest

from lepton_radiometry_studio.domain import ThermalFrame
from lepton_radiometry_studio.storage.stills import load_still, save_still


def test_still_round_trip_preserves_radiometry(tmp_path) -> None:
    frame = ThermalFrame(
        raw=np.arange(12, dtype=np.uint16).reshape(3, 4) + 29000,
        timestamp_ns=987654321,
        temperature_scale=0.01,
        temperature_offset=-273.15,
        telemetry={"fpa_c": 29.3},
        camera_settings={"radiometric": True},
    )
    preview = np.zeros((3, 4, 3), dtype=np.uint8)

    saved = save_still(frame, tmp_path, preview, name="test_capture")
    loaded = load_still(saved)

    assert np.array_equal(loaded.raw, frame.raw)
    assert loaded.timestamp_ns == frame.timestamp_ns
    assert loaded.telemetry == frame.telemetry
    assert (saved / "thermal.tiff").exists()
    assert (saved / "preview.png").exists()
    metadata = json.loads((saved / "metadata.json").read_text())
    assert metadata["format_version"] == 1


def test_load_rejects_non_radiometric_image(tmp_path) -> None:
    plain_png = tmp_path / "ordinary.png"
    plain_png.write_bytes(b"not important")
    with pytest.raises(ValueError, match="metadata"):
        load_still(plain_png)


def test_default_capture_name_and_preview_are_openable(tmp_path) -> None:
    frame = ThermalFrame(
        raw=np.full((3, 4), 29315, dtype=np.uint16),
        timestamp_ns=123,
    )
    destination = save_still(
        frame,
        tmp_path,
        preview_rgb=np.zeros((3, 4, 3), dtype=np.uint8),
    )

    loaded = load_still(destination / "preview.png")

    assert destination.name.startswith("capture_still_")
    assert np.array_equal(loaded.raw, frame.raw)
