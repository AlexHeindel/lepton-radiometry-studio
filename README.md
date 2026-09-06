# Lepton Radiometry Studio

A native desktop application for viewing, inspecting, capturing, and recording
radiometric data from a FLIR Lepton 3.5. The same interface runs against a
direct SPI/I²C camera connection on Raspberry Pi and an optional simulated
camera on development computers.

## Current milestone

- Native PySide6 live viewer
- Raspberry Pi GPIO auto-detection and direct Lepton 3.5 VoSPI/CCI capture
- Synthetic 160 × 120 thermal stream at the Lepton frame rate
- Iron, inferno, grayscale, rainbow, and cool/warm palettes
- Dark appearance by default, with theme, palette, units, marker, range, and zoom controls under **View**
- Optional minimum/maximum markers in the viewer and visual exports
- Toggleable per-frame automatic dynamic range or a fixed temperature range
- Sensor-coordinate-accurate zoom and pan up to 16×
- Persistent point markers plus rectangle and circle ROI measurements
- Per-region minimum, maximum, average, and pixel count
- Per-pixel hover coordinates, raw value, and temperature
- Minimum, maximum, center, mean, and frame-rate measurements
- Celsius, Fahrenheit, and Kelvin display units
- Selectable PNG, 16-bit TIFF, NumPy, and metadata still outputs
- Self-contained still and video capture folders with timestamped names
- Selectable HDF5 radiometric recording and high-quality H.264 MP4 outputs
- HDF5 playback, play/pause, timeline scrubbing, and live pixel inspection
- Visible buttons for opening saved radiometric videos and stills for analysis
- Hardware-independent `FrameSource` interface

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

The application looks for a physical Lepton at startup. If it is not available,
the viewer stays black and reports **Camera not found**. Choose **Tools → Use
synthetic demo** to exercise the interface without camera hardware.

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

The PNG uses the palette, automatic or fixed display range, min/max markers,
point markers, and ROIs visible when the still is captured. The MP4 locks and
uses those same settings when recording starts. HDF5 and still metadata also
store the display recipe so it is restored for later analysis. MP4 is
convenient for ordinary video players but does not contain temperatures. When
selected, HDF5 keeps the original 16-bit measurements and per-frame metadata.
Lepton-sized previews are smoothly enlarged to 640 × 480 and encoded as
high-quality H.264 video; this improves viewing quality without inventing
additional sensor resolution.

To inspect a recording, click **Open .h5 video for analysis…** or choose
**File → Open radiometric recording…**, select the `.h5` file, then use
Play/Pause or the timeline. Hovering over the image continues to show the raw
value and temperature for the displayed frame.

Use the mouse wheel or the zoom buttons to zoom. In the default **Inspect /
hover** mode, left-, middle-, or right-drag pans the image. Choosing **Add point
marker**, **Draw rectangle ROI**, or **Draw circle ROI** temporarily assigns the
left mouse button to that measurement tool; middle- and right-drag continue to
pan. Measurements are calculated from the original radiometric pixels,
independent of palette, zoom, or display range. Saved markers and ROIs appear in
the measurement table, with one comparison row added for each measurement. The
Markers / ROIs panel is hidden by default; use **Tools → Show Markers / ROIs
panel** when it is needed.

To inspect a saved still, click **Open radiometric still for analysis…** and
select `preview.png`, `thermal.npy`, or `thermal.tiff` from its capture folder.
The application automatically loads the sibling raw data and metadata. A plain
PNG without those companion files can be viewed by an image viewer, but cannot
provide temperature measurements.

See [the recording format](docs/RECORDING_FORMAT.md) for the stored datasets and
a small Python analysis example.

## Run on Raspberry Pi 5

The FLIR Lepton Breakout Board v2.0 uses SPI for VoSPI image packets and I²C for
camera control. Connect it to the Pi as shown in the SparkFun hookup guide, then
enable both interfaces:

```bash
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
sudo reboot
```

After the reboot, install the app with the Raspberry Pi hardware dependencies:

```bash
git clone https://github.com/AlexHeindel/lepton-radiometry-studio.git
cd lepton-radiometry-studio
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[pi,dev]'
pytest
python -m lepton_radiometry_studio
```

The app verifies the Lepton control interface at I²C address `0x2a`, enables
TLinear radiometry at 0.01 K/count, and tries both `/dev/spidev0.0` (CE0, header
pin 24) and `/dev/spidev0.1` (CE1, header pin 26). It connects to the first chip
select that produces a complete four-segment Lepton 3 frame. To force one,
launch with `LEPTON_SPI_DEVICE=0.0` or `LEPTON_SPI_DEVICE=0.1`.

If detection fails, verify the operating-system interfaces and camera response:

```bash
ls -l /dev/spidev0.* /dev/i2c-1
sudo apt install i2c-tools
i2cdetect -r -y 1 0x2a 0x2a
```

The I²C scan should show `2a`. If the device files exist but the app reports a
permission error, add the desktop user to the hardware-access groups, then log
out and back in:

```bash
sudo usermod -aG spi,i2c,gpio "$USER"
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

## License

Lepton Radiometry Studio is open-source software released under the
[MIT License](LICENSE). Third-party attributions are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
