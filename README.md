# Lepton Radiometry Studio

A native desktop application for viewing, inspecting, capturing, and recording
radiometric data from a FLIR Lepton 3.5. The same interface runs against a
simulated camera on macOS and a hardware capture helper on Raspberry Pi 5.

## Current milestone

- Native PySide6 live viewer
- Synthetic 160 × 120 thermal stream at the Lepton frame rate
- Iron, inferno, grayscale, rainbow, and cool/warm palettes
- Per-pixel hover coordinates, raw value, and temperature
- Minimum, maximum, center, mean, and frame-rate measurements
- Celsius, Fahrenheit, and Kelvin display units
- Radiometric still bundles containing 16-bit TIFF, NumPy data, metadata, and PNG preview
- Paired HDF5 radiometric recording and colorized MP4 preview
- HDF5 playback, play/pause, timeline scrubbing, and live pixel inspection
- Hardware-independent `FrameSource` interface for the Raspberry Pi capture helper

## Set up on macOS

Python 3.11 is recommended. Python 3.9 and newer are supported.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
pytest
python -m lepton_radiometry_studio
```

The application starts with a synthetic camera, so no Lepton hardware is
required on the development Mac.

## Record and play back

Starting a recording creates two files with the same timestamped name:

```text
recording_2026-09-04_153000.h5   # radiometric source of truth
recording_2026-09-04_153000.mp4  # convenient colorized video
```

The MP4 uses the palette selected when recording starts. It is convenient for
ordinary video players but does not contain temperatures. The HDF5 file keeps
the original 16-bit measurements and per-frame metadata.

To inspect a recording, choose **File → Open radiometric recording…**, select
the `.h5` file, then use Play/Pause or the timeline. Hovering over the image
continues to show the raw value and temperature for the displayed frame.

See [the recording format](docs/RECORDING_FORMAT.md) for the stored datasets and
a small Python analysis example.

## Run on Raspberry Pi 5

The graphical and radiometric code is cross-platform. The Lepton-specific
capture layer will be supplied by a small native helper that owns timing-sensitive
SPI frame assembly, resynchronization, FFC, and TLinear configuration.

```bash
git clone https://github.com/AlexHeindel/lepton-radiometry-studio.git
cd lepton-radiometry-studio
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
python -m lepton_radiometry_studio
```

## Data integrity

Rendered PNG and video exports are visual products; they do not retain a
temperature measurement at every pixel. Lepton Radiometry Studio keeps the
original 16-bit frame and radiometric scale/offset alongside previews.

The default TLinear conversion is:

```text
temperature_C = raw_count * 0.01 - 273.15
```

Scale and offset are stored per frame and are never inferred from the palette.
