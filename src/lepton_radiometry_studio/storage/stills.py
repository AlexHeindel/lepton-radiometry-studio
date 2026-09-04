from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from lepton_radiometry_studio.domain import ThermalFrame


def save_still(
    frame: ThermalFrame,
    parent: Path,
    preview_rgb: Optional[np.ndarray] = None,
    name: Optional[str] = None,
) -> Path:
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    capture_name = name or datetime.now().strftime("capture_%Y-%m-%d_%H%M%S_%f")
    destination = parent / capture_name
    destination.mkdir(parents=False, exist_ok=False)

    np.save(destination / "thermal.npy", frame.raw, allow_pickle=False)
    Image.fromarray(frame.raw).save(destination / "thermal.tiff")
    metadata = {
        "format_version": 1,
        "timestamp_ns": frame.timestamp_ns,
        "width": frame.width,
        "height": frame.height,
        "dtype": "uint16",
        "temperature_scale": frame.temperature_scale,
        "temperature_offset": frame.temperature_offset,
        "telemetry": dict(frame.telemetry),
        "camera_settings": dict(frame.camera_settings),
    }
    (destination / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if preview_rgb is not None:
        preview = np.asarray(preview_rgb, dtype=np.uint8)
        if preview.shape != (*frame.shape, 3):
            raise ValueError("Preview must match frame dimensions and contain RGB channels")
        Image.fromarray(preview).save(destination / "preview.png")
    return destination


def load_still(path: Path) -> ThermalFrame:
    path = Path(path)
    directory = path if path.is_dir() else path.parent
    metadata_path = directory / "metadata.json"
    if not metadata_path.exists():
        raise ValueError("A radiometric still requires an accompanying metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    if path.is_dir() or path.suffix.lower() == ".npy":
        raw_path = directory / "thermal.npy" if path.is_dir() else path
        raw = np.load(raw_path, allow_pickle=False)
    elif path.suffix.lower() in {".tif", ".tiff"}:
        raw = np.asarray(Image.open(path), dtype=np.uint16)
    else:
        raise ValueError("Open a capture directory, thermal.npy, or thermal.tiff")

    return ThermalFrame(
        raw=np.asarray(raw, dtype=np.uint16),
        timestamp_ns=int(metadata["timestamp_ns"]),
        temperature_scale=float(metadata["temperature_scale"]),
        temperature_offset=float(metadata["temperature_offset"]),
        telemetry=metadata.get("telemetry", {}),
        camera_settings=metadata.get("camera_settings", {}),
    )
