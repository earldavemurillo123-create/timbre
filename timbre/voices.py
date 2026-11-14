"""Saved reference voices, stored as data/voices/<id>/reference.wav + meta.json."""

from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from . import audio as A
from .config import Settings


@dataclass
class Voice:
    id: str
    name: str
    created_at: float
    duration: float
    sample_rate: int
    consent: bool
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class VoiceLibrary:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.voices_dir
        self.root.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------- queries

    def list(self) -> list[Voice]:
        voices = []
        for meta in self.root.glob("*/meta.json"):
            try:
                voices.append(Voice(**json.loads(meta.read_text("utf-8"))))
            except (json.JSONDecodeError, TypeError):
                continue
        return sorted(voices, key=lambda v: v.created_at, reverse=True)

    def get(self, voice_id: str) -> Voice:
        meta = self._dir(voice_id) / "meta.json"
        if not meta.exists():
            raise KeyError(f"No saved voice with id '{voice_id}'")
        return Voice(**json.loads(meta.read_text("utf-8")))

    def reference_path(self, voice_id: str) -> Path:
        self.get(voice_id)
        return self._dir(voice_id) / "reference.wav"

    # -------------------------------------------------------------- changes

    def add(self, name: str, source: str | Path, consent: bool, notes: str = "") -> Voice:
        """Clean a raw clip and save it as a reusable voice."""
        if not consent:
            raise PermissionError(
                "Confirm you have permission to use this voice before saving it."
            )
        name = name.strip() or "Untitled voice"
        sr = self.settings.reference_sample_rate
        raw, _ = A.load_audio(source, target_sr=sr)
        cleaned = A.clean_reference(raw, sr, self.settings.max_reference_seconds)

        length = A.duration(cleaned, sr)
        if length < self.settings.min_reference_seconds:
            raise A.AudioError(
                f"This clip has only {length:.1f}s of speech after trimming silence. "
                f"Use at least {self.settings.min_reference_seconds:.0f} seconds; 10–30 seconds works best."
            )

        voice_id = f"{_slug(name)}-{uuid.uuid4().hex[:6]}"
        folder = self._dir(voice_id)
        folder.mkdir(parents=True)
        A.save_wav(folder / "reference.wav", cleaned, sr)

        voice = Voice(
            id=voice_id,
            name=name[:60],
            created_at=time.time(),
            duration=round(length, 2),
            sample_rate=sr,
            consent=True,
            notes=notes[:500],
        )
        (folder / "meta.json").write_text(json.dumps(voice.to_dict(), indent=2), "utf-8")
        return voice

    def rename(self, voice_id: str, name: str) -> Voice:
        voice = self.get(voice_id)
        voice.name = name.strip()[:60] or voice.name
        (self._dir(voice_id) / "meta.json").write_text(json.dumps(voice.to_dict(), indent=2), "utf-8")
        return voice

    def delete(self, voice_id: str) -> None:
        self.get(voice_id)
        shutil.rmtree(self._dir(voice_id))

    # -------------------------------------------------------------- helpers

    def _dir(self, voice_id: str) -> Path:
        if not re.fullmatch(r"[a-z0-9-]{1,80}", voice_id):
            raise KeyError(f"Invalid voice id '{voice_id}'")
        return self.root / voice_id


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40] or "voice"
