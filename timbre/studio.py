"""The synthesis service shared by the web server and the CLI.

A "take" is one generation: a single text, or a whole batch script. Each take lives in
data/takes/<id>/ with the audio, an .srt subtitle file and meta.json.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from . import audio as A
from .config import Settings
from .engines import Engine, create_engine
from .text import build_srt, chunk_text, parse_script
from .voices import VoiceLibrary

MAX_TEXT_CHARS = 5000
MAX_BATCH_LINES = 200


@dataclass
class Take:
    id: str
    number: int
    kind: str  # "single" or "batch"
    voice_id: str
    voice_name: str
    language: str
    speed: float
    text: str
    created_at: float
    duration: float
    engine: str
    files: dict[str, str] = field(default_factory=dict)  # role -> filename
    lines: list[dict] = field(default_factory=list)  # batch only: [{index, text, file, duration}]

    def to_dict(self) -> dict:
        return asdict(self)


class Studio:
    def __init__(self, settings: Settings, engine: Engine | None = None):
        self.settings = settings
        settings.ensure_dirs()
        self.voices = VoiceLibrary(settings)
        self.engine = engine or create_engine(settings.engine, settings.device)
        self._lock = threading.Lock()  # models are not thread-safe; one generation at a time

    def load(self) -> None:
        if not self.engine.loaded:
            self.engine.load()

    # ------------------------------------------------------------ generation

    def speak(self, voice_id: str, text: str, language: str = "en", speed: float = 1.0) -> Take:
        """Generate one take from free text. Long text is split into sentences."""
        text = text.strip()
        self._validate(text, language, speed)
        voice = self.voices.get(voice_id)
        ref = self.voices.reference_path(voice_id)

        chunks = chunk_text(text, self.settings.max_chunk_chars)
        with self._lock:
            rendered = [self._render(c, ref, language, speed) for c in chunks]

        sr = self.engine.sample_rate
        full, segments = self._join(chunks, rendered, sr, self.settings.sentence_pause)

        take = self._new_take("single", voice, language, speed, text, A.duration(full, sr))
        folder = self._take_dir(take.id)
        A.save_wav(folder / "take.wav", full, sr, comment=A.SYNTHETIC_NOTE)
        (folder / "take.srt").write_text(build_srt(segments), "utf-8")
        take.files = {"audio": "take.wav", "subtitles": "take.srt"}
        self._save_meta(take)
        return take

    def batch(self, voice_id: str, script: str, language: str = "en", speed: float = 1.0) -> Take:
        """Generate one clip per script line, plus a merged file and subtitles."""
        lines = parse_script(script)
        if not lines:
            raise ValueError("The script is empty. Write one line per clip; lines starting with # are skipped.")
        if len(lines) > MAX_BATCH_LINES:
            raise ValueError(f"Scripts are limited to {MAX_BATCH_LINES} lines; this one has {len(lines)}.")
        self._validate(" ".join(lines), language, speed)
        voice = self.voices.get(voice_id)
        ref = self.voices.reference_path(voice_id)
        sr = self.engine.sample_rate

        clips: list[np.ndarray] = []
        with self._lock:
            for line in lines:
                chunks = chunk_text(line, self.settings.max_chunk_chars)
                rendered = [self._render(c, ref, language, speed) for c in chunks]
                clip, _ = self._join(chunks, rendered, sr, self.settings.sentence_pause)
                clips.append(clip)

        merged, segments = self._join(lines, clips, sr, self.settings.line_pause)
        take = self._new_take("batch", voice, language, speed, "\n".join(lines), A.duration(merged, sr))
        folder = self._take_dir(take.id)

        width = len(str(len(lines)))
        for i, (line, clip) in enumerate(zip(lines, clips), 1):
            name = f"line-{i:0{width}d}.wav"
            A.save_wav(folder / name, clip, sr, comment=A.SYNTHETIC_NOTE)
            take.lines.append({"index": i, "text": line, "file": name, "duration": round(A.duration(clip, sr), 2)})

        A.save_wav(folder / "take.wav", merged, sr, comment=A.SYNTHETIC_NOTE)
        (folder / "take.srt").write_text(build_srt(segments), "utf-8")
        take.files = {"audio": "take.wav", "subtitles": "take.srt"}
        self._save_meta(take)
        return take

    # ------------------------------------------------------------ takes

    def list_takes(self, limit: int = 50) -> list[Take]:
        takes = []
        for meta in self.settings.takes_dir.glob("*/meta.json"):
            try:
                takes.append(Take(**json.loads(meta.read_text("utf-8"))))
            except (json.JSONDecodeError, TypeError):
                continue
        takes.sort(key=lambda t: t.created_at, reverse=True)
        return takes[:limit]

    def take_file(self, take_id: str, filename: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", filename) or ".." in filename:
            raise KeyError("Invalid file name")
        path = self._take_dir(take_id) / filename
        if not path.exists():
            raise KeyError(f"No file '{filename}' in take '{take_id}'")
        return path

    def delete_take(self, take_id: str) -> None:
        folder = self._take_dir(take_id)
        if not folder.exists():
            raise KeyError(f"No take with id '{take_id}'")
        for item in folder.iterdir():
            item.unlink()
        folder.rmdir()

    # ------------------------------------------------------------ internals

    def _validate(self, text: str, language: str, speed: float) -> None:
        if not text:
            raise ValueError("Write something for the voice to say.")
        if len(text) > MAX_TEXT_CHARS:
            raise ValueError(f"Text is limited to {MAX_TEXT_CHARS} characters; this has {len(text)}.")
        if language not in self.engine.languages:
            raise ValueError(f"The {self.engine.label} engine doesn't support language '{language}'.")
        if not 0.5 <= speed <= 2.0:
            raise ValueError("Speed must be between 0.5 and 2.0.")

    def _render(self, text: str, ref: Path, language: str, speed: float) -> np.ndarray:
        wav = self.engine.synthesize(text, ref, language=language, speed=speed)
        return A.trim_silence(np.asarray(wav, dtype=np.float32), self.engine.sample_rate, threshold_db=-50, pad=0.05)

    @staticmethod
    def _join(texts: list[str], clips: list[np.ndarray], sr: int, pause: float):
        """Concatenate clips with pauses and return (audio, subtitle segments)."""
        segments, cursor = [], 0.0
        for i, (text, clip) in enumerate(zip(texts, clips)):
            if i:
                cursor += pause
            length = A.duration(clip, sr)
            segments.append((cursor, cursor + length, text))
            cursor += length
        return A.concat(clips, sr, pause), segments

    def _new_take(self, kind, voice, language, speed, text, length) -> Take:
        number = max((t.number for t in self.list_takes(limit=10_000)), default=0) + 1
        take_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
        self._take_dir(take_id).mkdir(parents=True)
        return Take(
            id=take_id,
            number=number,
            kind=kind,
            voice_id=voice.id,
            voice_name=voice.name,
            language=language,
            speed=speed,
            text=text,
            created_at=time.time(),
            duration=round(length, 2),
            engine=self.engine.name,
        )

    def _take_dir(self, take_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9-]{1,60}", take_id):
            raise KeyError(f"Invalid take id '{take_id}'")
        return self.settings.takes_dir / take_id

    def _save_meta(self, take: Take) -> None:
        (self._take_dir(take.id) / "meta.json").write_text(json.dumps(take.to_dict(), indent=2), "utf-8")
