# Architecture

```text
macOS                              Raspberry Pi 5

SyntheticSource ─┐                FLIR Lepton 3.5
StillFileSource ─┼─ ThermalFrame       │ SPI / I²C
RecordingSource ─┘       │         LeptonSource
                         │              │ complete uint16 frames
                         ├──────────────┘
                         │
              processing and measurements
                         │
                  PySide6 interface
                         │
          stills / HDF5 + MP4 / visual exports
```

## Boundary rules

1. Every source emits complete `ThermalFrame` objects.
2. Temperature calculations use raw values plus frame scale/offset, never RGB colors.
3. The UI does not import Linux SPI or I²C libraries; `LeptonSource` loads them
   only when a live Pi camera is detected.
4. Live display may drop stale frames to keep latency low; recording must never drop
   a frame silently.
5. Hardware recovery, VoSPI segmentation, FFC, and TLinear configuration belong in
   the Pi-only source adapter.
6. When selected, HDF5 is the recording source of truth. MP4 files are
   palette-rendered visual companions and never a temperature data source.

## Raspberry Pi live source

At startup, the application probes I²C bus 1 for a responsive Lepton command
interface, enables 0.01 K TLinear radiometry, and tries SPI0 CE0 followed by CE1.
The adapter validates packet order and segment identifiers before constructing a
contiguous `uint16[120][160]` `ThermalFrame`. If detection or later acquisition
fails, the UI clears stale imagery and returns to a black camera-not-found state.
