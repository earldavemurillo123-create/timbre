"""Demo engine: no model, no GPU, no downloads.

It produces a hummed, speech-like placeholder whose pitch follows the reference voice
and whose length follows the text. Use it to work on the interface, run tests, or
record a README demo on a machine that can't run a real model.
"""

from __future__ import annotations

import zlib
from pathlib import Path

import numpy as np

from ..audio import load_audio
from .base import Engine


class DemoEngine(Engine):
    name = "demo"
    label = "Demo (no model)"
    languages = ["en", "es", "fr", "de", "it", "pt", "ja", "ko", "zh-cn"]

    @property
    def sample_rate(self) -> int:
        return 22050

    def load(self) -> None:
        self._pitch_cache: dict[str, float] = {}
        self.loaded = True

    def synthesize(self, text: str, reference_wav: Path, language: str = "en", speed: float = 1.0) -> np.ndarray:
        sr = self.sample_rate
        f0 = self._reference_pitch(reference_wav)
        rng = np.random.default_rng(zlib.crc32(text.encode("utf-8")))

        syllables = max(1, int(sum(_vowel_groups(w) for w in text.split())))
        syllable_len = 0.19 / max(0.5, min(speed, 2.0))
        pieces = []
        for i in range(syllables):
            n = int(sr * syllable_len * rng.uniform(0.75, 1.25))
            t = np.arange(n) / sr
            drift = 1 + 0.08 * np.sin(2 * np.pi * rng.uniform(0.5, 2) * t) - 0.05 * (i / syllables)
            phase = 2 * np.pi * np.cumsum(f0 * drift) / sr
            tone = (np.sin(phase) + 0.45 * np.sin(2 * phase) + 0.2 * np.sin(3 * phase))
            envelope = np.sin(np.pi * np.linspace(0, 1, n)) ** 1.5
            pieces.append(tone * envelope * rng.uniform(0.5, 1.0))
            if rng.random() < 0.18:  # word gaps
                pieces.append(np.zeros(int(sr * 0.06)))
        audio = np.concatenate(pieces) * 0.25
        return audio.astype(np.float32)

    def _reference_pitch(self, path: Path) -> float:
        key = str(path)
        if key not in self._pitch_cache:
            try:
                audio, sr = load_audio(path, target_sr=16000)
                self._pitch_cache[key] = estimate_pitch(audio, sr)
            except Exception:
                self._pitch_cache[key] = 160.0
        return self._pitch_cache[key]


def _vowel_groups(word: str) -> int:
    groups, prev = 0, False
    for ch in word.lower():
        is_vowel = ch in "aeiouy"
        if is_vowel and not prev:
            groups += 1
        prev = is_vowel
    return max(1, groups)


def estimate_pitch(audio: np.ndarray, sr: int, fmin: float = 70, fmax: float = 400) -> float:
    """Rough median pitch via autocorrelation over voiced frames."""
    frame = int(sr * 0.04)
    estimates = []
    for start in range(0, len(audio) - frame, frame):
        x = audio[start : start + frame]
        if np.sqrt(np.mean(x**2)) < 0.02:
            continue
        x = x - x.mean()
        corr = np.correlate(x, x, mode="full")[frame - 1 :]
        lo, hi = int(sr / fmax), int(sr / fmin)
        if hi >= len(corr):
            continue
        lag = lo + int(np.argmax(corr[lo:hi]))
        if corr[lag] > 0.3 * corr[0]:
            estimates.append(sr / lag)
    return float(np.median(estimates)) if estimates else 160.0
