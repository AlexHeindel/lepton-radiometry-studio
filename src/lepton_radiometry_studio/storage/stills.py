from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional

import numpy as np
from PIL import Image

from lepton_radiometry_studio.domain import ThermalFrame


def save_still(
    frame: ThermalFrame,
    parent: Path,
    preview_rgb: Optional[np.ndarray] = None,
    name: Optional[str] = None,
    save_png: bool = True,
    save_tiff: bool = True,
    save_numpy: bool = True,
    save_metadata: bool = True,
    preview_palette: Optional[str] = None,
    preview_show_extrema: Optional[bool] = None,
    display_settings: Optional[Mapping[str, Any]] = None,
) -> Path:
    if not any((save_png, save_tiff, save_numpy, save_metadata)):
        raise ValueError("Select at least one still file type")
    if save_png and preview_rgb is None:
        raise ValueError("A PNG export requires a rendered preview")
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    capture_name = name or datetime.now().strftime(
        "capture_still_%Y-%m-%d_%H%M%S_%f"
    )
    destination = parent / capture_name
    destination.mkdir(parents=False, exist_ok=False)

    if save_numpy:
        np.save(destination / "thermal.npy", frame.raw, allow_pickle=False)
    if save_tiff:
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
    if (
        preview_palette is not None
        or preview_show_extrema is not None
        or display_settings
    ):
        display = {
            "palette": preview_palette,
            "show_extrema": preview_show_extrema,
        }
        if display_settings:
            display.update(dict(display_settings))
        metadata["display"] = display
    if save_metadata:
        (destination / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if save_png:
        preview = np.asarray(preview_rgb, dtype=np.uint8)
        if preview.ndim != 3 or preview.shape[2] != 3:
            raise ValueError("Preview must contain RGB channels")
        Image.fromarray(preview).save(destination / "preview.png")
    return destination


def load_still(path: Path) -> ThermalFrame:
    path = Path(path)
    directory = path if path.is_dir() else path.parent
    metadata_path = directory / "metadata.json"
    if not metadata_path.exists():
        raise ValueError("A radiometric still requires an accompanying metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    if path.is_dir() or path.name in {"preview.png", "metadata.json"}:
        numpy_path = directory / "thermal.npy"
        tiff_path = directory / "thermal.tiff"
        if numpy_path.exists():
            raw = np.load(numpy_path, allow_pickle=False)
        elif tiff_path.exists():
            raw = np.asarray(Image.open(tiff_path), dtype=np.uint16)
        else:
            raise ValueError(
                "The capture folder requires thermal.npy or thermal.tiff for analysis"
            )
    elif path.suffix.lower() == ".npy":
        raw_path = path
        raw = np.load(raw_path, allow_pickle=False)
    elif path.suffix.lower() in {".tif", ".tiff"}:
        raw = np.asarray(Image.open(path), dtype=np.uint16)
    else:
        raise ValueError(
            "Open preview.png, thermal.npy, or thermal.tiff from a radiometric capture"
        )

    return ThermalFrame(
        raw=np.asarray(raw, dtype=np.uint16),
        timestamp_ns=int(metadata["timestamp_ns"]),
        temperature_scale=float(metadata["temperature_scale"]),
        temperature_offset=float(metadata["temperature_offset"]),
        telemetry=metadata.get("telemetry", {}),
        camera_settings=metadata.get("camera_settings", {}),
    )


def load_still_display_settings(path: Path) -> Mapping[str, Any]:
    path = Path(path)
    directory = path if path.is_dir() else path.parent
    metadata_path = directory / "metadata.json"
    if not metadata_path.exists():
        return {}
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    display = metadata.get("display", {})
    return display if isinstance(display, dict) else {}
