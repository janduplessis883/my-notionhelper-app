#!/usr/bin/env python3
"""Split an NHS candidate export into one UTF-8 text file per candidate."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import NamedTuple


END_MARKER = re.compile(r"^\s*protected\s*$(?:\n\s*No\s*$)?", re.IGNORECASE | re.MULTILINE)
REFERENCE = re.compile(r"\s+AR-\d{6}-\d+\b", re.IGNORECASE)
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
ACADEMIC_QUALIFICATIONS = re.compile(
    r"^\s*Academic Qualifications\s*$",
    re.IGNORECASE | re.MULTILINE,
)


class CandidateRecord(NamedTuple):
    name: str
    reference: str
    text: str


def candidate_name(record: str) -> str:
    """Read the candidate name from the first line containing an AR reference."""
    for line in record.splitlines():
        match = REFERENCE.search(line)
        if match:
            name = line[: match.start()].strip()
            if name:
                return name
    raise ValueError("Could not find a candidate name before an AR reference")


def candidate_reference(record: str) -> str:
    match = re.search(r"\bAR-\d{6}-\d+\b", record, re.IGNORECASE)
    if not match:
        raise ValueError("Could not find an AR application reference")
    return match.group(0).upper()


def safe_filename(name: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", name).strip(" .")
    return cleaned or "unnamed_candidate"


def record_to_candidate(record: str) -> CandidateRecord:
    name = candidate_name(record)
    reference = candidate_reference(record)
    return CandidateRecord(name=name, reference=reference, text=record)


def split_by_academic_qualification_anchors(text: str) -> list[CandidateRecord]:
    """Split candidate records from application-section starts, not page footers."""

    anchors = list(ACADEMIC_QUALIFICATIONS.finditer(text))
    candidates: list[CandidateRecord] = []
    seen_references: set[str] = set()

    for index, anchor in enumerate(anchors):
        next_anchor = anchors[index + 1].start() if index + 1 < len(anchors) else len(text)
        record = text[anchor.start() : next_anchor].strip()
        if not re.search(r"\bAR-\d{6}-\d+\b", record, re.IGNORECASE):
            continue

        candidate = record_to_candidate(record)
        if candidate.reference in seen_references:
            continue

        seen_references.add(candidate.reference)
        candidates.append(candidate)

    return candidates


def split_candidate_records(text: str) -> list[CandidateRecord]:
    """Split extracted application text into candidate records without writing files."""

    anchored_candidates = split_by_academic_qualification_anchors(text)
    if anchored_candidates:
        return anchored_candidates

    records: list[str] = []
    start = 0

    for match in END_MARKER.finditer(text):
        chunk = text[start : match.end()].strip()
        start = match.end()
        if chunk:
            records.append(chunk + "\n")

    trailing = text[start:].strip()
    if trailing:
        has_candidate_heading = re.search(
            r"^NHS GP - Health Care Assistant\b.*$",
            trailing,
            re.IGNORECASE | re.MULTILINE,
        )
        has_candidate_reference = re.search(r"\bAR-\d{6}-\d+\b", trailing, re.IGNORECASE)
        if has_candidate_heading and has_candidate_reference:
            records.append(trailing + "\n")

    candidates: list[CandidateRecord] = []

    for index, record in enumerate(records):
        # The first chunk may contain a report/index before the first candidate.
        first_job_heading = re.search(
            r"^NHS GP - Health Care Assistant\b.*$", record, re.IGNORECASE | re.MULTILINE
        )
        if not first_job_heading:
            if not re.search(r"\bAR-\d{6}-\d+\b", record, re.IGNORECASE):
                continue
        else:
            record = record[first_job_heading.start() :]

        try:
            candidates.append(record_to_candidate(record))
        except ValueError:
            continue

    return candidates


def split_candidates(source: Path, output_dir: Path) -> list[Path]:
    text = source.read_text(encoding="utf-8-sig")
    records = split_candidate_records(text)

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for record in records:
        name = record.name
        path = output_dir / f"{safe_filename(name)}.txt"
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite duplicate output: {path}")
        path.write_text(record.text, encoding="utf-8")
        written.append(path)

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Path to candidates.txt")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("candidate_split"),
        help="Output directory (default: ./candidate_split)",
    )
    args = parser.parse_args()

    files = split_candidates(args.source, args.output_dir)
    print(f"Created {len(files)} candidate files in {args.output_dir.resolve()}")
    for path in files:
        print(path.name)


if __name__ == "__main__":
    main()
