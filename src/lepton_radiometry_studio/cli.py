from __future__ import annotations

import argparse
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from lepton_radiometry_studio.processing import PALETTES, render_visual_export
from lepton_radiometry_studio.sources.base import FrameSource
from lepton_radiometry_studio.sources.lepton import LeptonSource
from lepton_radiometry_studio.sources.synthetic import SyntheticSource
from lepton_radiometry_studio.storage.recordings import RadiometricRecordingSession
from lepton_radiometry_studio.storage.stills import save_still


STILL_FORMATS = ("png", "tiff", "npy", "json")
VIDEO_FORMATS = ("hdf5", "mp4")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lepton-capture",
        description=(
            "Capture radiometric stills or videos from a FLIR Lepton without "
            "starting the desktop interface."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""examples:
  lepton-capture still --output ./captures --format png tiff npy json --auto-range
  lepton-capture video --output ./captures --format hdf5 mp4 --duration 60 \
    --palette Inferno --range 10 45
  lepton-capture video --output ./captures --format hdf5 --frames 500 --auto-range
""",
    )
    subparsers = parser.add_subparsers(
        dest="capture_mode", title="capture modes", required=True
    )

    still = subparsers.add_parser(
        "still", help="capture one still frame", description="Capture one still frame."
    )
    _add_common_arguments(still)
    still.add_argument(
        "--format",
        nargs="+",
        choices=STILL_FORMATS,
        required=True,
        help="one or more outputs: png tiff npy json",
    )

    video = subparsers.add_parser(
        "video",
        help="capture a video recording",
        description="Capture a bounded video or record until interrupted.",
    )
    _add_common_arguments(video)
    video.add_argument(
        "--format",
        nargs="+",
        choices=VIDEO_FORMATS,
        required=True,
        help="one or more outputs: hdf5 mp4",
    )
    limit = video.add_mutually_exclusive_group(required=True)
    limit.add_argument(
        "--duration",
        type=_positive_float,
        metavar="SECONDS",
        help="stop after this many seconds",
    )
    limit.add_argument(
        "--frames",
        type=_positive_int,
        metavar="COUNT",
        help="stop after this many frames",
    )
    limit.add_argument(
        "--until-interrupted",
        action="store_true",
        help="record until Ctrl+C",
    )
    return parser


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        metavar="FOLDER",
        help="parent folder for the timestamped capture folder",
    )
    parser.add_argument(
        "--palette",
        choices=tuple(PALETTES),
        default="Iron",
        help="palette for PNG or MP4 output (default: %(default)s)",
    )
    display_range = parser.add_mutually_exclusive_group(required=True)
    display_range.add_argument(
        "--auto-range",
        action="store_true",
        help="map each frame's measured minimum and maximum to the palette",
    )
    display_range.add_argument(
        "--range",
        dest="fixed_range",
        type=float,
        nargs=2,
        metavar=("MIN_C", "MAX_C"),
        help="use a fixed display range in degrees Celsius",
    )
    parser.add_argument(
        "--show-extrema",
        action="store_true",
        help="draw minimum and maximum markers on PNG or MP4 output",
    )
    parser.add_argument(
        "--source",
        choices=("camera", "synthetic"),
        default="camera",
        help="capture source; synthetic is intended for testing (default: %(default)s)",
    )
    parser.add_argument(
        "--spi-device",
        metavar="BUS.DEVICE",
        help="use a specific SPI device instead of camera auto-detection",
    )
    parser.add_argument(
        "--i2c-bus",
        type=int,
        default=1,
        metavar="BUS",
        help="I2C bus used with --spi-device (default: %(default)s)",
    )
    parser.add_argument(
        "--ffc",
        action="store_true",
        help="run flat-field correction before capturing",
    )


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.fixed_range is not None:
        minimum_c, maximum_c = args.fixed_range
        if not math.isfinite(minimum_c) or not math.isfinite(maximum_c):
            parser.error("--range values must be finite")
        if maximum_c <= minimum_c:
            parser.error("--range MAX_C must be greater than MIN_C")
    if args.source == "synthetic" and args.spi_device is not None:
        parser.error("--spi-device cannot be used with --source synthetic")
    if args.source == "synthetic" and args.ffc:
        parser.error("--ffc cannot be used with --source synthetic")
    if args.i2c_bus < 0:
        parser.error("--i2c-bus must be zero or greater")


def _open_source(args: argparse.Namespace) -> FrameSource:
    if args.source == "synthetic":
        source: FrameSource = SyntheticSource()
        source.start()
        return source
    if args.spi_device is None:
        return LeptonSource.autodetect()
    try:
        bus_text, device_text = args.spi_device.split(".", 1)
        bus, device = int(bus_text), int(device_text)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("--spi-device must look like '0.0' or '0.1'") from exc
    if bus < 0 or device < 0:
        raise ValueError("--spi-device bus and device must be zero or greater")
    source = LeptonSource(spi_bus=bus, spi_device=device, i2c_bus=args.i2c_bus)
    source.prepare()
    return source


def _range_values(args: argparse.Namespace) -> tuple[Optional[float], Optional[float]]:
    if args.fixed_range is None:
        return None, None
    return float(args.fixed_range[0]), float(args.fixed_range[1])


def _display_settings(args: argparse.Namespace) -> dict[str, object]:
    minimum_c, maximum_c = _range_values(args)
    return {
        "palette": args.palette,
        "show_extrema": bool(args.show_extrema),
        "automatic_range": args.fixed_range is None,
        "minimum_c": minimum_c,
        "maximum_c": maximum_c,
        "point_markers": [],
        "regions": [],
    }


def _capture_still(args: argparse.Namespace, source: FrameSource) -> Path:
    frame = source.next_frame()
    formats = set(args.format)
    minimum_c, maximum_c = _range_values(args)
    preview = None
    if "png" in formats:
        preview = render_visual_export(
            frame,
            palette=args.palette,
            show_extrema=args.show_extrema,
            minimum_c=minimum_c,
            maximum_c=maximum_c,
        )
    return save_still(
        frame,
        args.output,
        preview_rgb=preview,
        save_png="png" in formats,
        save_tiff="tiff" in formats,
        save_numpy="npy" in formats,
        save_metadata="json" in formats,
        preview_palette=args.palette,
        preview_show_extrema=args.show_extrema,
        display_settings=_display_settings(args),
    )


def _capture_video(args: argparse.Namespace, source: FrameSource) -> tuple[Path, int]:
    first_frame = source.next_frame()
    capture_name = datetime.now().strftime("capture_video_%Y-%m-%d_%H%M%S_%f")
    destination = args.output / capture_name
    destination.mkdir(parents=True, exist_ok=False)
    formats = set(args.format)
    hdf5_path = destination / f"{capture_name}.h5" if "hdf5" in formats else None
    video_path = destination / f"{capture_name}.mp4" if "mp4" in formats else None
    minimum_c, maximum_c = _range_values(args)
    recording: Optional[RadiometricRecordingSession] = None
    try:
        recording = RadiometricRecordingSession(
            hdf5_path,
            video_path,
            first_frame,
            palette=args.palette,
            fps=source.nominal_fps,
            show_extrema=args.show_extrema,
            automatic_range=args.fixed_range is None,
            minimum_c=minimum_c,
            maximum_c=maximum_c,
        )
        recording.append(first_frame)
        started = time.monotonic()
        next_synthetic_frame = started + 1.0 / source.nominal_fps
        while True:
            if args.frames is not None and recording.frame_count >= args.frames:
                break
            if args.duration is not None and time.monotonic() - started >= args.duration:
                break
            if isinstance(source, SyntheticSource):
                delay = next_synthetic_frame - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                next_synthetic_frame += 1.0 / source.nominal_fps
            recording.append(source.next_frame())
        frame_count = recording.frame_count
        recording.close()
        return destination, frame_count
    except BaseException:
        if recording is not None:
            recording.close()
        try:
            destination.rmdir()
        except OSError:
            pass
        raise


def run(args: argparse.Namespace) -> tuple[Path, Optional[int]]:
    source = _open_source(args)
    try:
        if args.ffc:
            source.run_ffc()
        if args.capture_mode == "still":
            return _capture_still(args, source), None
        destination, frame_count = _capture_video(args, source)
        return destination, frame_count
    finally:
        source.stop()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_args(parser, args)
    try:
        destination, frame_count = run(args)
    except KeyboardInterrupt:
        print("\nCapture interrupted; finalized files written so far.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"lepton-capture: error: {exc}", file=sys.stderr)
        return 1
    if frame_count is None:
        print(f"Saved still to {destination}")
    else:
        print(f"Saved {frame_count} frames to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
