# Radiometric recording format

Lepton Radiometry Studio can write a measurement-grade HDF5 file, a convenient
MP4 preview, or both. When selected, the HDF5 file is the source of truth.

## HDF5 datasets

New format-version 2 recordings contain:

| Dataset | Shape | Purpose |
| --- | --- | --- |
| `/frames` | `(frame_count, height, width)` | Original `uint16` radiometric values |
| `/timestamps_ns` | `(frame_count,)` | Capture timestamps in nanoseconds |
| `/temperature_scales` | `(frame_count,)` | Scale used to convert each frame to Celsius |
| `/temperature_offsets` | `(frame_count,)` | Offset used to convert each frame to Celsius |
| `/telemetry_json` | `(frame_count,)` | Per-frame sensor telemetry |
| `/camera_settings_json` | `(frame_count,)` | Per-frame radiometry and camera settings |

Frames are chunked and compressed losslessly with GZIP. Format-version 1 files
created by the first application release remain readable; their shared
scale/offset and first-frame metadata are loaded from file attributes.

For each pixel:

```text
temperature_C = raw_value * temperature_scale + temperature_offset
```

## Application playback

Click **Open .h5 video for analysis…** or choose
**File → Open radiometric recording…**, then select an `.h5` or `.hdf5` file.
The existing thermal viewer provides:

- play and pause;
- timeline scrubbing;
- palette changes without altering measurements;
- Celsius, Fahrenheit, or Kelvin display;
- per-pixel raw value and temperature on hover;
- minimum, maximum, mean, and center measurements for every frame;
- radiometric still capture from any playback frame.

## Python analysis

```python
from pathlib import Path

from lepton_radiometry_studio.storage import Hdf5RecordingReader

with Hdf5RecordingReader(Path("recording.h5")) as recording:
    frame = recording.frame(0)
    temperatures_c = frame.temperatures_celsius()
    print(recording.nominal_fps, recording.duration_seconds)
    print(temperatures_c.min(), temperatures_c.mean(), temperatures_c.max())
```

## MP4 companion

The MP4 contains the palette-rendered RGB frames at the recording source's
nominal frame rate. A 160 × 120 Lepton preview is enlarged to 640 × 480 with
Lanczos scaling and encoded using high-quality H.264 when the encoder is
available. The palette and min/max-marker setting are captured when recording
starts and locked until recording stops. The MP4 can be opened in QuickTime,
VLC, browsers, and ordinary video editors. It intentionally does not claim to
be radiometric: compression and color mapping discard the raw sensor values
needed for temperature lookup.
