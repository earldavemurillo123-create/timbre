"""Audio loading, cleanup and saving.

Only numpy and scipy are required. Formats other than WAV (mp3, m4a, ogg, webm from the
browser recorder) are decoded with ffmpeg, which must be on PATH for those formats.
"""

from __future__ import annotations

import io
import shutil
import struct
import subprocess
import warnings
from math import gcd
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly


class AudioError(ValueError):
    """Raised when an audio file can't be read or isn't usable."""


# ---------------------------------------------------------------- loading

def load_audio(path: str | Path, target_sr: int | None = None) -> tuple[np.ndarray, int]:
    """Load any audio file as mono float32 in [-1, 1]. Optionally resample."""
    path = Path(path)
    if not path.exists():
        raise AudioError(f"File not found: {path}")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", wavfile.WavFileWarning)  # our own LIST/INFO tag
            sr, data = wavfile.read(path)
        audio = _to_float(data)
    except Exception:
        audio, sr = _decode_with_ffmpeg(path)

    audio = to_mono(audio)
    if target_sr and sr != target_sr:
        audio = resample(audio, sr, target_sr)
        sr = target_sr
    return audio.astype(np.float32), sr


def _to_float(data: np.ndarray) -> np.ndarray:
    if data.dtype == np.int16:
        return data.astype(np.float32) / 32768.0
    if data.dtype == np.int32:
        return data.astype(np.float32) / 2147483648.0
    if data.dtype == np.uint8:
        return (data.astype(np.float32) - 128.0) / 128.0
    return data.astype(np.float32)


def _decode_with_ffmpeg(path: Path, sr: int = 44100) -> tuple[np.ndarray, int]:
    if shutil.which("ffmpeg") is None:
        raise AudioError(
            "This file isn't a plain WAV, and ffmpeg isn't installed to decode it. "
            "Install ffmpeg or upload a .wav file."
        )
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0 or not result.stdout:
        message = result.stderr.decode(errors="ignore").strip().splitlines()
        raise AudioError(f"Couldn't decode {path.name}: {message[-1] if message else 'unknown error'}")
    return np.frombuffer(result.stdout, dtype=np.float32).copy(), sr


# ---------------------------------------------------------------- processing

def to_mono(audio: np.ndarray) -> np.ndarray:
    return audio.mean(axis=1) if audio.ndim == 2 else audio


def resample(audio: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to:
        return audio
    g = gcd(sr_from, sr_to)
    return resample_poly(audio, sr_to // g, sr_from // g).astype(np.float32)


def trim_silence(audio: np.ndarray, sr: int, threshold_db: float = -40.0, pad: float = 0.1) -> np.ndarray:
    """Cut leading and trailing silence, keeping a little padding."""
    if audio.size == 0:
        return audio
    frame = max(1, int(sr * 0.02))
    n_frames = len(audio) // frame
    if n_frames == 0:
        return audio
    frames = audio[: n_frames * frame].reshape(n_frames, frame)
    rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-12)
    loud = np.where(20 * np.log10(rms / (np.max(rms) + 1e-12)) > threshold_db)[0]
    if loud.size == 0:
        return audio[:0]
    start = max(0, loud[0] * frame - int(pad * sr))
    end = min(len(audio), (loud[-1] + 1) * frame + int(pad * sr))
    return audio[start:end]


def normalize(audio: np.ndarray, target_dbfs: float = -20.0, peak_limit: float = 0.95) -> np.ndarray:
    """Bring loudness to a target RMS level without clipping."""
    rms = np.sqrt(np.mean(audio**2)) if audio.size else 0.0
    if rms < 1e-6:
        return audio
    gain = 10 ** (target_dbfs / 20) / rms
    out = audio * gain
    peak = np.max(np.abs(out))
    if peak > peak_limit:
        out *= peak_limit / peak
    return out.astype(np.float32)


def silence(seconds: float, sr: int) -> np.ndarray:
    return np.zeros(int(round(seconds * sr)), dtype=np.float32)


def concat(chunks: list[np.ndarray], sr: int, pause: float) -> np.ndarray:
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    gap = silence(pause, sr)
    parts: list[np.ndarray] = []
    for i, chunk in enumerate(chunks):
        if i:
            parts.append(gap)
        parts.append(chunk.astype(np.float32))
    return np.concatenate(parts)


def duration(audio: np.ndarray, sr: int) -> float:
    return len(audio) / float(sr)


def clean_reference(audio: np.ndarray, sr: int, max_seconds: float) -> np.ndarray:
    """The standard cleanup applied to every reference voice clip."""
    audio = audio - np.mean(audio)  # remove DC offset
    audio = trim_silence(audio, sr)
    audio = audio[: int(max_seconds * sr)]
    return normalize(audio)


# ---------------------------------------------------------------- saving

SYNTHETIC_NOTE = "Synthetic speech generated with Timbre (AI voice clone)."


def save_wav(path: str | Path, audio: np.ndarray, sr: int, comment: str | None = None) -> Path:
    """Save 16-bit PCM WAV. An optional comment is stored in a RIFF INFO chunk,
    which we use to mark generated files as synthetic."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)

    buffer = io.BytesIO()
    wavfile.write(buffer, sr, pcm)
    data = buffer.getvalue()

    if comment:
        data = _add_info_chunk(data, {"ICMT": comment, "ISFT": "Timbre"})

    path.write_bytes(data)
    return path


def _add_info_chunk(wav_bytes: bytes, tags: dict[str, str]) -> bytes:
    body = b"INFO"
    for key, value in tags.items():
        text = value.encode("utf-8") + b"\x00"
        if len(text) % 2:
            text += b"\x00"
        body += key.encode("ascii") + struct.pack("<I", len(text)) + text
    chunk = b"LIST" + struct.pack("<I", len(body)) + body
    riff_body = wav_bytes[8:] + chunk
    return b"RIFF" + struct.pack("<I", len(riff_body)) + riff_body


def read_info_comment(path: str | Path) -> str | None:
    """Return the ICMT comment of a WAV file, if any."""
    data = Path(path).read_bytes()
    idx = data.find(b"ICMT")
    if idx < 0:
        return None
    size = struct.unpack("<I", data[idx + 4 : idx + 8])[0]
    return data[idx + 8 : idx + 8 + size].rstrip(b"\x00").decode("utf-8", errors="ignore")
