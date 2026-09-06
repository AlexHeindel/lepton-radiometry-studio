import subprocess
import sys
from pathlib import Path

import h5py
import pytest

from lepton_radiometry_studio import cli


def test_importing_cli_does_not_load_gui_or_optional_writers() -> None:
    check = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import lepton_radiometry_studio.cli; "
                "assert 'PySide6' not in sys.modules; "
                "assert 'h5py' not in sys.modules; "
                "assert 'av' not in sys.modules; "
                "assert 'PIL' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert check.returncode == 0, check.stderr


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["still", "--format", "png", "--auto-range"],
        ["still", "--output", ".", "--auto-range"],
        ["still", "--output", ".", "--format", "png"],
        [
            "video",
            "--output",
            ".",
            "--format",
            "hdf5",
            "--auto-range",
        ],
    ],
)
def test_required_cli_arguments_are_enforced(arguments) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(arguments)

    assert exc_info.value.code == 2


def test_cli_rejects_an_inverted_fixed_range() -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                "still",
                "--output",
                ".",
                "--format",
                "png",
                "--range",
                "40",
                "10",
                "--source",
                "synthetic",
            ]
        )

    assert exc_info.value.code == 2


def test_cli_captures_selected_still_outputs(tmp_path: Path) -> None:
    result = cli.main(
        [
            "still",
            "--output",
            str(tmp_path),
            "--format",
            "png",
            "json",
            "--palette",
            "Grayscale",
            "--range",
            "10",
            "45",
            "--source",
            "synthetic",
        ]
    )

    assert result == 0
    destination = next(tmp_path.glob("capture_still_*"))
    assert {path.name for path in destination.iterdir()} == {
        "metadata.json",
        "preview.png",
    }


def test_cli_captures_an_exact_number_of_hdf5_frames(tmp_path: Path) -> None:
    result = cli.main(
        [
            "video",
            "--output",
            str(tmp_path),
            "--format",
            "hdf5",
            "--frames",
            "3",
            "--auto-range",
            "--source",
            "synthetic",
        ]
    )

    assert result == 0
    recording_path = next(tmp_path.glob("capture_video_*/*.h5"))
    with h5py.File(recording_path, "r") as recording:
        assert recording["frames"].shape[0] == 3


def test_cli_help_names_capture_modes_and_required_options(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["video", "--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "--output FOLDER" in output
    assert "--format" in output
    assert "--auto-range" in output
    assert "--range MIN_C MAX_C" in output
    assert "--duration SECONDS" in output
    assert "--frames COUNT" in output
