# Lepton Radiometry Studio

A native desktop application for viewing, inspecting, capturing, and recording
radiometric data from a FLIR Lepton 3.5. The same interface runs against a
simulated camera on macOS and a hardware capture helper on Raspberry Pi 5.

## Current milestone

- Native PySide6 live viewer
- Synthetic 160 × 120 thermal stream at the Lepton frame rate
- Iron, inferno, grayscale, rainbow, and cool/warm palettes
- Optional minimum/maximum markers in the viewer and visual exports
- Per-pixel hover coordinates, raw value, and temperature
- Minimum, maximum, center, mean, and frame-rate measurements
- Celsius, Fahrenheit, and Kelvin display units
- Selectable PNG, 16-bit TIFF, NumPy, and metadata still outputs
- Self-contained still and video capture folders with timestamped names
- Selectable HDF5 radiometric recording and high-quality H.264 MP4 outputs
- HDF5 playback, play/pause, timeline scrubbing, and live pixel inspection
- Visible buttons for opening saved radiometric videos and stills for analysis
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

Still captures and video recordings are saved in self-contained folders. The
checkboxes directly beneath each capture button determine which files are
created, so a folder may contain all or only some of the files shown here:

```text
capture_still_2026-09-04_153000_123456/
  thermal.npy
  thermal.tiff
  metadata.json
  preview.png

capture_video_2026-09-04_153100_654321/
  capture_video_2026-09-04_153100_654321.h5   # radiometric source of truth
  capture_video_2026-09-04_153100_654321.mp4  # convenient colorized video
```

The PNG uses the palette and min/max-marker setting visible when the still is
captured. The MP4 locks and uses those same display settings when recording
starts. MP4 is convenient for ordinary video players but does not contain
temperatures. When selected, HDF5 keeps the original 16-bit measurements and
per-frame metadata. Lepton-sized previews are smoothly enlarged to 640 × 480
and encoded as high-quality H.264 video; this improves viewing quality without
inventing additional sensor resolution.

To inspect a recording, click **Open .h5 video for analysis…** or choose
**File → Open radiometric recording…**, select the `.h5` file, then use
Play/Pause or the timeline. Hovering over the image continues to show the raw
value and temperature for the displayed frame.

To inspect a saved still, click **Open radiometric still for analysis…** and
select `preview.png`, `thermal.npy`, or `thermal.tiff` from its capture folder.
The application automatically loads the sibling raw data and metadata. A plain
PNG without those companion files can be viewed by an image viewer, but cannot
provide temperature measurements.

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
temperature measurement at every pixel. Select NPY, TIFF, and metadata for a
radiometric still, or HDF5 for a radiometric video, when temperature analysis
must remain possible.

The default TLinear conversion is:

```text
temperature_C = raw_count * 0.01 - 273.15
```

Scale and offset are stored per frame and are never inferred from the palette.
