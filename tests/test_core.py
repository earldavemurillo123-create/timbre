"""Core tests. They use the demo engine, so no model or GPU is needed."""

from pathlib import Path

import numpy as np
import pytest

from timbre import audio as A
from timbre.config import Settings
from timbre.studio import Studio
from timbre.text import build_srt, chunk_text, parse_script, split_sentences


# ----------------------------------------------------------------- fixtures

@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings(data_dir=tmp_path / "data", engine="demo")
    s.ensure_dirs()
    return s


@pytest.fixture
def studio(settings) -> Studio:
    st = Studio(settings)
    st.load()
    return st


@pytest.fixture
def clip(tmp_path) -> Path:
    """Eight seconds of a voiced-ish tone padded with silence."""
    sr = 22050
    t = np.arange(sr * 8) / sr
    tone = 0.3 * np.sin(2 * np.pi * 140 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
    audio = np.concatenate([np.zeros(sr), tone, np.zeros(sr)]).astype(np.float32)
    return A.save_wav(tmp_path / "clip.wav", audio, sr)


# ----------------------------------------------------------------- text

def test_split_sentences_keeps_abbreviations():
    assert split_sentences("Hello there.  Dr. Smith is here! Ready?") == [
        "Hello there.", "Dr. Smith is here!", "Ready?",
    ]


def test_chunk_text_respects_limit():
    long_sentence = "word " * 120
    chunks = chunk_text(long_sentence, max_chars=100)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)


def test_parse_script_skips_comments_and_blanks():
    assert parse_script("# title\nLine one.\n\n  Line two.  \n") == ["Line one.", "Line two."]


def test_build_srt_format():
    srt = build_srt([(0, 1.5, "Hi."), (2, 3.25, "Bye.")])
    assert "1\n00:00:00,000 --> 00:00:01,500\nHi." in srt
    assert "00:00:02,000 --> 00:00:03,250" in srt


# ----------------------------------------------------------------- audio

def test_trim_and_normalize():
    sr = 16000
    audio = np.concatenate([np.zeros(sr), 0.05 * np.ones(sr), np.zeros(sr)]).astype(np.float32)
    trimmed = A.trim_silence(audio, sr)
    assert len(trimmed) < len(audio)
    assert np.max(np.abs(A.normalize(trimmed))) <= 0.95 + 1e-6


def test_resample_length():
    audio = np.zeros(48000, dtype=np.float32)
    assert len(A.resample(audio, 48000, 24000)) == 24000


def test_saved_wav_is_marked_synthetic(tmp_path):
    path = A.save_wav(tmp_path / "x.wav", np.zeros(1000, dtype=np.float32), 22050, comment=A.SYNTHETIC_NOTE)
    assert A.read_info_comment(path) == A.SYNTHETIC_NOTE
    audio, sr = A.load_audio(path)  # still a valid WAV
    assert sr == 22050 and len(audio) == 1000


# ----------------------------------------------------------------- voices

def test_add_voice_requires_consent(studio, clip):
    with pytest.raises(PermissionError):
        studio.voices.add("Narrator", clip, consent=False)


def test_add_voice_rejects_short_clip(studio, tmp_path):
    short = A.save_wav(tmp_path / "short.wav", 0.3 * np.ones(22050, dtype=np.float32), 22050)
    with pytest.raises(A.AudioError):
        studio.voices.add("Short", short, consent=True)


def test_voice_lifecycle(studio, clip):
    voice = studio.voices.add("Narrator", clip, consent=True)
    assert voice.duration == pytest.approx(8.2, abs=0.3)  # silence trimmed, small padding kept
    assert [v.id for v in studio.voices.list()] == [voice.id]
    assert studio.voices.rename(voice.id, "Host").name == "Host"
    studio.voices.delete(voice.id)
    assert studio.voices.list() == []


def test_invalid_voice_id_is_rejected(studio):
    with pytest.raises(KeyError):
        studio.voices.get("../../etc")


# ----------------------------------------------------------------- generation

def test_speak_creates_take_with_subtitles(studio, clip, settings):
    voice = studio.voices.add("Narrator", clip, consent=True)
    take = studio.speak(voice.id, "First sentence. Second sentence here.")
    folder = settings.takes_dir / take.id
    assert take.number == 1 and take.duration > 0
    assert (folder / "take.wav").exists()
    assert (folder / "take.srt").read_text().count("-->") == 2


def test_batch_creates_one_file_per_line(studio, clip, settings):
    voice = studio.voices.add("Narrator", clip, consent=True)
    take = studio.batch(voice.id, "# notes\nLine one.\nLine two.\nLine three.")
    folder = settings.takes_dir / take.id
    assert [l["file"] for l in take.lines] == ["line-1.wav", "line-2.wav", "line-3.wav"]
    assert all((folder / l["file"]).exists() for l in take.lines)
    assert studio.list_takes()[0].id == take.id


def test_take_numbers_increase_after_delete(studio, clip):
    voice = studio.voices.add("Narrator", clip, consent=True)
    first = studio.speak(voice.id, "One.")
    second = studio.speak(voice.id, "Two.")
    studio.delete_take(first.id)
    assert studio.speak(voice.id, "Three.").number == second.number + 1


@pytest.mark.parametrize("text,lang,speed", [("", "en", 1.0), ("Hi.", "xx", 1.0), ("Hi.", "en", 3.0)])
def test_speak_validation(studio, clip, text, lang, speed):
    voice = studio.voices.add("Narrator", clip, consent=True)
    with pytest.raises(ValueError):
        studio.speak(voice.id, text, lang, speed)


def test_take_file_blocks_path_traversal(studio, clip):
    voice = studio.voices.add("Narrator", clip, consent=True)
    take = studio.speak(voice.id, "Hello.")
    with pytest.raises(KeyError):
        studio.take_file(take.id, "../meta.json")
