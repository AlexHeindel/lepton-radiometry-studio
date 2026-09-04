import numpy as np

from lepton_radiometry_studio.sources import SyntheticSource


def test_synthetic_source_matches_lepton_dimensions_and_radiometry() -> None:
    source = SyntheticSource()
    frame = source.next_frame()

    assert frame.shape == (120, 160)
    assert frame.raw.dtype == np.uint16
    assert frame.camera_settings["radiometric"] is True
    assert 10.0 < frame.statistics().minimum_c < 35.0
    assert 30.0 < frame.statistics().maximum_c < 55.0


def test_synthetic_scene_moves() -> None:
    source = SyntheticSource()
    first = source.next_frame()
    second = source.next_frame()
    assert not np.array_equal(first.raw, second.raw)

