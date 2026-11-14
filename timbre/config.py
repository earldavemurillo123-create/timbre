"""Paths and defaults. Every value can be overridden with an environment variable."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else default


@dataclass
class Settings:
    # Where saved reference voices and generated takes live.
    data_dir: Path = field(default_factory=lambda: _env_path("TIMBRE_DATA_DIR", ROOT / "data"))

    # Which synthesis engine to load: "xtts" (real cloning) or "demo" (no model, for UI work).
    engine: str = field(default_factory=lambda: os.environ.get("TIMBRE_ENGINE", "xtts"))

    # "auto" picks CUDA when available, otherwise CPU.
    device: str = field(default_factory=lambda: os.environ.get("TIMBRE_DEVICE", "auto"))

    # Reference clips are cleaned and stored at this sample rate.
    reference_sample_rate: int = 22050

    # Reference clip length limits, in seconds.
    min_reference_seconds: float = 3.0
    max_reference_seconds: float = 30.0

    # Text longer than this is split into chunks before synthesis.
    max_chunk_chars: int = 220

    # Silence inserted between sentences / batch lines, in seconds.
    sentence_pause: float = 0.25
    line_pause: float = 0.6

    @property
    def voices_dir(self) -> Path:
        return self.data_dir / "voices"

    @property
    def takes_dir(self) -> Path:
        return self.data_dir / "takes"

    def ensure_dirs(self) -> None:
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self.takes_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
