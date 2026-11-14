"""The interface every synthesis engine implements.

To add a new model (F5-TTS, OpenVoice, ...), subclass ``Engine``, implement
``load`` and ``synthesize``, and register it in ``engines/__init__.py``.
Nothing else in the app needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class EngineInfo:
    name: str
    label: str
    sample_rate: int
    languages: list[str]
    device: str
    is_demo: bool = False


class Engine(ABC):
    name: str = "base"
    label: str = "Base engine"
    languages: list[str] = ["en"]

    def __init__(self, device: str = "auto"):
        self.device = resolve_device(device)
        self.loaded = False

    @property
    @abstractmethod
    def sample_rate(self) -> int: ...

    @abstractmethod
    def load(self) -> None:
        """Load model weights. Called once at startup."""

    @abstractmethod
    def synthesize(self, text: str, reference_wav: Path, language: str = "en", speed: float = 1.0) -> np.ndarray:
        """Return mono float32 audio at ``self.sample_rate`` for one short chunk of text."""

    def info(self) -> EngineInfo:
        return EngineInfo(
            name=self.name,
            label=self.label,
            sample_rate=self.sample_rate,
            languages=list(self.languages),
            device=self.device,
            is_demo=self.name == "demo",
        )


def resolve_device(device: str) -> str:
    if device != "auto":
        return device
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"
