# Architecture

```text
macOS                              Raspberry Pi 5

SyntheticSource ─┐                FLIR Lepton 3.5
StillFileSource ─┼─ ThermalFrame       │ SPI / I²C
RecordingSource ─┘       │         native capture helper
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
3. The UI does not import Linux SPI or I²C libraries.
4. Live display may drop stale frames to keep latency low; recording must never drop
   a frame silently.
5. Hardware recovery, VoSPI segmentation, FFC, and TLinear configuration belong in
   the native Pi helper.
6. When selected, HDF5 is the recording source of truth. MP4 files are
   palette-rendered visual companions and never a temperature data source.

## Pi helper protocol (planned)

The helper will use a versioned local Unix-domain socket protocol. Each frame
message will contain a fixed-size header followed by a contiguous little-endian
`uint16[120][160]` payload. Control messages will cover status, FFC, reconnect,
and shutdown. The Python adapter will validate dimensions, payload length,
monotonic sequence numbers, timestamps, and radiometric parameters before
constructing a `ThermalFrame`.
