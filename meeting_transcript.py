"""Decode uploaded meeting transcript files."""

import html
from pathlib import Path
import re


def convert_vtt_to_text(vtt_text: str) -> str:
    """Convert WebVTT cues to readable text while retaining cue context."""
    normalized = vtt_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    cues = []

    for block in re.split(r"\n\s*\n", normalized):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        block_type = lines[0].split(maxsplit=1)[0].upper()
        if block_type in {"WEBVTT", "NOTE", "STYLE", "REGION"}:
            continue

        timing_index = next(
            (index for index, line in enumerate(lines) if "-->" in line),
            None,
        )
        if timing_index is None:
            continue

        timing = lines[timing_index]
        start, raw_end = (part.strip() for part in timing.split("-->", maxsplit=1))
        end = raw_end.split(maxsplit=1)[0]
        content_lines = lines[timing_index + 1 :]
        if not content_lines:
            continue

        content = " ".join(content_lines)
        content = re.sub(r"<v(?:\.[^ >]+)*\s+([^>]+)>", r"\1: ", content)
        content = re.sub(r"<[^>]+>", "", content)
        content = html.unescape(content)
        content = re.sub(r"\s+", " ", content).strip()
        if content:
            cues.append(f"[{start} --> {end}] {content}")

    if not cues:
        raise ValueError("The WebVTT file contains no transcript cues.")
    return "\n".join(cues)


def decode_transcript_upload(filename: str, payload: bytes) -> str:
    """Decode a supported transcript upload into agent-ready text."""
    suffix = Path(filename).suffix.lower()
    if suffix not in {".txt", ".vtt"}:
        raise ValueError("Only .txt and .vtt transcript files are supported.")

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("The transcript must be encoded as UTF-8.") from exc

    if not text.strip():
        raise ValueError("The uploaded transcript is empty.")
    if suffix == ".vtt":
        return convert_vtt_to_text(text)
    return text
