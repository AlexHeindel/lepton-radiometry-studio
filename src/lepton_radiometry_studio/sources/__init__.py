from importlib import import_module
from typing import Any

__all__ = [
    "CameraUnavailableSource",
    "FrameSource",
    "Hdf5PlaybackSource",
    "LeptonFrameTimeout",
    "LeptonSource",
    "LeptonUnavailableError",
    "StillFileSource",
    "SyntheticSource",
]

_EXPORTS = {
    "CameraUnavailableSource": (".unavailable", "CameraUnavailableSource"),
    "FrameSource": (".base", "FrameSource"),
    "Hdf5PlaybackSource": (".recording", "Hdf5PlaybackSource"),
    "LeptonFrameTimeout": (".lepton", "LeptonFrameTimeout"),
    "LeptonSource": (".lepton", "LeptonSource"),
    "LeptonUnavailableError": (".lepton", "LeptonUnavailableError"),
    "StillFileSource": (".file", "StillFileSource"),
    "SyntheticSource": (".synthetic", "SyntheticSource"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value
