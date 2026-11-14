"""Text handling: sentence splitting, chunking and script parsing."""

from __future__ import annotations

import re

# Split after . ! ? … (and CJK equivalents) followed by whitespace or end of text.
_SENTENCE_END = re.compile(r"(?<=[.!?…。！？])[\"')\]]*\s+")
_ABBREVIATIONS = {"mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "st.", "vs.", "etc.", "e.g.", "i.e."}


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    text = normalize_whitespace(text)
    if not text:
        return []
    raw = _SENTENCE_END.split(text)
    sentences: list[str] = []
    for piece in raw:
        piece = piece.strip()
        if not piece:
            continue
        # Re-join pieces that were split after an abbreviation like "Dr."
        if sentences and sentences[-1].split()[-1].lower() in _ABBREVIATIONS:
            sentences[-1] = f"{sentences[-1]} {piece}"
        else:
            sentences.append(piece)
    return sentences


def chunk_text(text: str, max_chars: int = 220) -> list[str]:
    """Split text into chunks of whole sentences, each at most ``max_chars`` long.

    A single sentence longer than the limit is split at commas, then at spaces.
    Most voice models degrade on long inputs, so this keeps each request short.
    """
    chunks: list[str] = []
    for sentence in split_sentences(text):
        if len(sentence) <= max_chars:
            chunks.append(sentence)
        else:
            chunks.extend(_split_long(sentence, max_chars))
    return chunks


def _split_long(sentence: str, max_chars: int) -> list[str]:
    parts: list[str] = []
    current = ""
    for clause in re.split(r"(?<=[,;:])\s+", sentence):
        words = clause.split(" ") if len(clause) > max_chars else [clause]
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) <= max_chars or not current:
                current = candidate
            else:
                parts.append(current)
                current = word
    if current:
        parts.append(current)
    return parts


def parse_script(script: str) -> list[str]:
    """One line per clip. Blank lines and lines starting with # are skipped."""
    lines = []
    for line in script.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def format_srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(segments: list[tuple[float, float, str]]) -> str:
    """segments: (start_seconds, end_seconds, text)."""
    blocks = []
    for i, (start, end, text) in enumerate(segments, 1):
        blocks.append(f"{i}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text}\n")
    return "\n".join(blocks)
