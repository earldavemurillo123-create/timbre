"""Coqui XTTS-v2 engine: zero-shot voice cloning from a short reference clip.

Install:  pip install coqui-tts
Model license: Coqui Public Model License (non-commercial). The first run downloads
the weights (~1.8 GB) and asks you to accept the license; set COQUI_TOS_AGREED=1 to
accept it non-interactively.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import Engine

MODEL_ID = "tts_models/multilingual/multi-dataset/xtts_v2"


class XTTSEngine(Engine):
    name = "xtts"
    label = "XTTS-v2"
    languages = [
        "en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru",
        "nl", "cs", "ar", "zh-cn", "ja", "hu", "ko", "hi",
    ]

    def __init__(self, device: str = "auto"):
        super().__init__(device)
        self._tts = None
        self._sr = 24000

    @property
    def sample_rate(self) -> int:
        return self._sr

    def load(self) -> None:
        try:
            from TTS.api import TTS
        except ImportError as exc:
            raise RuntimeError(
                "XTTS needs the coqui-tts package. Install it with `pip install coqui-tts`, "
                "or start Timbre with `--engine demo` to try the interface without a model."
            ) from exc

        self._tts = TTS(MODEL_ID).to(self.device)
        synth = getattr(self._tts, "synthesizer", None)
        if synth is not None and getattr(synth, "output_sample_rate", None):
            self._sr = int(synth.output_sample_rate)
        self.loaded = True

    def synthesize(self, text: str, reference_wav: Path, language: str = "en", speed: float = 1.0) -> np.ndarray:
        if self._tts is None:
            raise RuntimeError("Engine not loaded")
        wav = self._tts.tts(
            text=text,
            speaker_wav=str(reference_wav),
            language=language,
            speed=speed,
            split_sentences=False,  # Timbre splits text itself so it can time subtitles.
        )
        return np.asarray(wav, dtype=np.float32)
