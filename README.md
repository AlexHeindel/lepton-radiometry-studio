# Lepton Radiometry Studio

Lepton Radiometry Studio is a set of three Python tools for viewing and
capturing radiometric data from a FLIR Lepton 3.5. They share the same camera,
rendering, and file-format code but target different workloads and Raspberry Pi
resource levels.

## Choose the right tool

| Tool | Purpose | Start it with | Inputs |
| --- | --- | --- | --- |
| **Studio** | Full live viewing, capture, saved-file playback, and temperature analysis | `lepton-radiometry-studio` | GPIO camera, synthetic stream, radiometric stills, and HDF5 recordings |
| **Lite** | Low-overhead graphical live viewing and capture | `lepton-radiometry-lite` | GPIO camera or synthetic stream |
| **CLI** | Headless, scriptable still and video capture | `lepton-capture …` | GPIO camera or synthetic stream |

Use Studio on a desktop or a capable Raspberry Pi when interactive analysis is
important. Use Lite when a Pi needs a live preview and capture buttons but not
analysis. Use the CLI for the smallest runtime footprint, unattended captures,
shell scripts, or a Raspberry Pi without a desktop environment.

## Compatibility

Python 3.9 and newer are supported; Python 3.11 is recommended. Automated tests
run on macOS and Linux.

| Environment | Studio | Lite | CLI | Physical camera |
| --- | --- | --- | --- | --- |
| Raspberry Pi OS with desktop, SPI, and I²C | Full feature set | Full feature set | Full feature set | Supported |
| Headless Raspberry Pi OS with SPI and I²C | Requires a display server | Requires a display server | Full feature set | Supported through CLI |
| Other Linux desktop | Saved/synthetic data; live capture if compatible `/dev` interfaces are present | Synthetic data; live capture if compatible `/dev` interfaces are present | Synthetic data; live capture if compatible `/dev` interfaces are present | Hardware-dependent and not specifically tested |
| macOS | Saved-file analysis and synthetic demo | Synthetic demo | Synthetic capture | Not supported by the GPIO backend |
| Windows | Not currently tested or supported | Not currently tested or supported | Not currently tested or supported | Not supported by the GPIO backend |

Studio and Lite require a graphical desktop supported by PySide6. The CLI does
not start Qt or require a display server. It also defers loading Pillow, h5py,
and PyAV until a selected output format needs them.

### Compatible cameras and connections

The live-camera backend targets a radiometric **FLIR Lepton 3.5** on a breakout
board that exposes both of these Raspberry Pi GPIO connections:

- SPI/VoSPI for 160 × 120 thermal frame data;
- I²C/CCI at address `0x2a` for camera control, TLinear radiometry, telemetry,
  reboot recovery, and flat-field correction.

Auto-detection checks I²C bus 1 and SPI0 chip selects CE0 and CE1
(`/dev/spidev0.0` and `/dev/spidev0.1`). The current backend does **not**
support USB/UVC thermal cameras, PureThermal USB mode, Raspberry Pi CSI, Ethernet
or network cameras, or non-radiometric image-only camera feeds. Those connection
types need separate `FrameSource` adapters.

The hardware code does not depend on Raspberry Pi 5-specific APIs, but Pi 5 is
the primary target. Older or lower-memory Pis should prefer CLI first and Lite
second; actual frame rate and MP4 encoding performance depend on the board,
operating system, storage, and installed codec support.

## Installation

Create a virtual environment and install the application:

```bash
git clone https://github.com/AlexHeindel/lepton-radiometry-studio.git
cd lepton-radiometry-studio
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

For development and tests:

```bash
python -m pip install -e '.[dev]'
pytest
```

On a Raspberry Pi, include the SPI and I²C Python dependencies:

```bash
python -m pip install -e '.[pi]'
```

If the project was already installed before the Lite and CLI tools were added,
rerun the appropriate editable-install command so their executable entry points
are created.

## Studio

### Purpose

Studio is the complete desktop application. In addition to live viewing and
capture, it can reopen radiometric stills and HDF5 videos for analysis. It is
the right tool for inspecting temperatures, comparing regions, or reviewing a
recording after collection.

Studio provides:

- live GPIO camera auto-detection and a synthetic development stream;
- Iron, inferno, grayscale, rainbow, and cool/warm palettes;
- automatic per-frame or fixed Celsius display ranges;
- zoom and pan up to 16×;
- cursor temperature, raw pixel value, minimum, maximum, mean, and center data;
- persistent point markers and rectangle/circle regions of interest;
- region minimum, maximum, average, and pixel count;
- Celsius, Fahrenheit, and Kelvin display;
- selectable PNG, TIFF, NPY, and JSON still outputs;
- selectable HDF5 radiometric and MP4 visual video outputs;
- HDF5 playback with play/pause and timeline scrubbing.

### Start Studio

After installation:

```bash
lepton-radiometry-studio
```

From a source checkout, this equivalent command is also available:

```bash
python -m lepton_radiometry_studio
```

Studio attempts to connect to a physical camera at startup. If none is found,
the canvas reports **Camera not found**. Choose **Tools → Use synthetic demo**
to exercise the interface without hardware, or use **Retry camera** after fixing
the connection.

To analyze an HDF5 recording, click **Open .h5 video for analysis…** or choose
**File → Open radiometric recording…**. To analyze a still, click
**Open radiometric still for analysis…** and select `preview.png`,
`thermal.npy`, or `thermal.tiff` from a capture folder. Studio reads the sibling
metadata and restores the saved display recipe.

The Markers / ROIs panel is hidden by default. Enable it with
**Tools → Show Markers / ROIs panel**. In **Inspect / hover** mode, drag to pan.
Select a point, rectangle, or circle tool to add persistent measurements; middle-
and right-drag remain available for panning.

## Lite

### Purpose

Lite keeps Studio's image-left/sidebar-right layout while removing saved-file
analysis, playback, measurement tables, markers, ROIs, unit conversion, and
uploads. Its sidebar contains only Source, Capture, and Display controls. It is
intended for Raspberry Pis that need a graphical live view and manual capture
without the full Studio workload.

Lite supports camera auto-detection, retry, flat-field correction, live frame
rate, palette selection, automatic or fixed display range, all four still
formats, and both video formats. Minimum/maximum overlays are disabled so the
live path avoids their statistics calculation.

### Start Lite

After installation:

```bash
lepton-radiometry-lite
```

From a source checkout:

```bash
python -m lepton_radiometry_studio.lite_main
```

Lite attempts to connect to the GPIO camera at startup. Click **Retry camera**
after correcting a disconnected camera, **Run FFC** to perform flat-field
correction on a connected Lepton, or choose **Camera → Use synthetic demo** for
a hardware-free test.

Select the desired still checkboxes before clicking **Capture radiometric
still**. Select HDF5, MP4, or both before clicking **Start radiometric
recording**. Lite writes the same self-contained capture folders as Studio.

## CLI

### Purpose

The CLI captures without opening a graphical interface. It is suitable for SSH
sessions, scheduled jobs, services, automated experiments, and the smallest
Raspberry Pi runtime footprint. The command fails with a concise error and a
nonzero exit status if camera connection or writing fails.

### Start the CLI

Display general or mode-specific help:

```bash
lepton-capture --help
lepton-capture still --help
lepton-capture video --help
```

The capture mode, `--output`, `--format`, and either `--auto-range` or
`--range MIN_C MAX_C` are required. Video additionally requires exactly one
stopping condition: `--duration SECONDS`, `--frames COUNT`, or
`--until-interrupted`.

Capture a still with all available outputs:

```bash
lepton-capture still \
  --output ./captures \
  --format png tiff npy json \
  --palette Iron \
  --auto-range
```

Capture a 60-second HDF5 and MP4 recording with a fixed Celsius range:

```bash
lepton-capture video \
  --output ./captures \
  --format hdf5 mp4 \
  --duration 60 \
  --palette Inferno \
  --range 10 45
```

Capture exactly 500 radiometric frames without the MP4 encoding workload:

```bash
lepton-capture video \
  --output ./captures \
  --format hdf5 \
  --frames 500 \
  --auto-range
```

Record until Ctrl+C, finalizing the files before exiting:

```bash
lepton-capture video \
  --output ./captures \
  --format hdf5 \
  --until-interrupted \
  --auto-range
```

Useful optional flags include:

- `--palette NAME` for visual PNG/MP4 output;
- `--show-extrema` to draw minimum and maximum markers on visual output;
- `--ffc` to run flat-field correction before capture;
- `--spi-device 0.0 --i2c-bus 1` to bypass SPI auto-detection;
- `--source synthetic` for a hardware-free end-to-end capture test.

`--ffc` and `--spi-device` are camera-only options and cannot be combined with
the synthetic source. The default source is `camera`.

## Capture folders and file compatibility

All three tools write timestamped, self-contained folders. The selected format
options determine which files are present:

```text
capture_still_2026-09-04_153000_123456/
  thermal.npy       # original uint16 array
  thermal.tiff      # original 16-bit radiometric pixels
  metadata.json     # conversion, telemetry, and display recipe
  preview.png       # palette-rendered visual image

capture_video_2026-09-04_153100_654321/
  capture_video_2026-09-04_153100_654321.h5   # radiometric source of truth
  capture_video_2026-09-04_153100_654321.mp4  # visual companion
```

PNG and MP4 are ordinary visual files compatible with common image viewers,
video players, browsers, and editors. They do not retain a temperature at every
pixel. NPY is directly readable by NumPy. TIFF stores the original 16-bit pixel
values. HDF5 stores original frames, timestamps, per-frame conversion values,
telemetry, camera settings, and the display recipe. See
[the recording format](docs/RECORDING_FORMAT.md) for the schema and a Python
analysis example.

The PNG uses the selected palette and range. Studio also includes its visible
min/max and measurement overlays. The MP4 locks its visual settings when
recording begins. Lepton-sized previews are enlarged from 160 × 120 to
640 × 480 for convenient viewing without claiming additional sensor resolution.

## Raspberry Pi camera setup

Enable SPI and I²C before trying any tool with the physical camera:

```bash
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
sudo reboot
```

After rebooting, verify the interfaces and camera response:

```bash
ls -l /dev/spidev0.* /dev/i2c-1
sudo apt install i2c-tools
i2cdetect -r -y 1 0x2a 0x2a
```

The I²C scan should show `2a`. If the device files exist but access is denied,
add the user running the tools to the hardware groups, then log out and back in:

```bash
sudo usermod -aG spi,i2c,gpio "$USER"
```

The camera backend enables TLinear radiometry at 0.01 K/count and tries CE0
before CE1. Studio and Lite can be forced to one chip select with
`LEPTON_SPI_DEVICE=0.0` or `LEPTON_SPI_DEVICE=0.1`. The CLI accepts the same
environment variable during auto-detection or the explicit `--spi-device`
option.

## Data integrity

Rendered colors are never used to calculate temperature. The default TLinear
conversion is:

```text
temperature_C = raw_count * 0.01 - 273.15
```

Scale and offset are stored with radiometric captures. Select NPY or TIFF plus
JSON for a measurement-capable still, or HDF5 for a measurement-capable video.
MP4 and PNG should be treated only as convenient visual exports.

## License

Lepton Radiometry Studio is open-source software released under the
[MIT License](LICENSE). Third-party attributions are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
