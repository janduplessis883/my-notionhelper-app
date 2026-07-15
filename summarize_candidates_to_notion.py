#!/usr/bin/env python3
"""Summarize candidate text files with an OpenAI-compatible LLM and append to Notion."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from notionhelper import NotionHelper
import requests


DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_MODEL = "gpt-oss-20b-MXFP4-Q8"
DEFAULT_DATA_SOURCE_ID = "f67b501f-cd6e-4cca-92cd-c4282b51182f"
DEFAULT_JOB_ROLE = "Healthcare Assistant position in UK general practice"

ASSESSMENT_PROMPT = """\
Summarize this job applicant in concise bullet points. Clearly list their last 3
employers, with the current or most recent role first. They are applying for:

{job_role}

Assess whether the evidence shows the role-specific competencies, experience,
qualifications, and personal attributes needed for this role. Do not invent or
infer skills, employers, dates, or qualifications that are not present in the
candidate text. Explicitly label missing or unclear evidence as "Not evidenced".
End with a suitability score out of 10 and a brief evidence-based reason.

Return Markdown in exactly this section order:

### Candidate Name
### Employment History (Current role first)
- List no more than the last 3 employers, including role and dates when available.
### Education & Professional Training
- One concise paragraph.
### Core Experience
- State the evidenced period of relevant experience (for example, 5 years), or say
  that the period cannot be determined reliably.
### Key Competencies
- Use bullet points, covering every required competency named above.
### Suitability for the role
- Concise assessment.
- **Suitability score: X/10** - Concise explanation of the score, based only on the supplied evidence.
Candidate text follows:

---
{candidate_text}
"""


@dataclass(frozen=True)
class LocalLLMSettings:
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key: str = "12345"
    max_tokens: int = 1400
    timeout: float = 180.0
    max_retries: int = 2
    delay: float = 0.0


def normalize_name(value: str) -> str:
    """Normalize a person's name for strict, case-insensitive matching."""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def generate_summary(
    base_url: str,
    api_key: str,
    model: str,
    candidate_text: str,
    max_tokens: int,
    assessment_prompt: str = ASSESSMENT_PROMPT,
    job_role: str = DEFAULT_JOB_ROLE,
    timeout: float = 180.0,
    max_retries: int = 2,
) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a careful UK general-practice recruitment assistant. "
                    "Use only the supplied application evidence and return Markdown."
                ),
            },
            {
                "role": "user",
                "content": assessment_prompt.format(
                    candidate_text=candidate_text,
                    job_role=job_role,
                ),
            },
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            summary = data["choices"][0]["message"]["content"]
            break
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                raise RuntimeError(f"Local LLM request failed: {exc}") from exc
            time.sleep(min(2 ** attempt, 8))
    else:
        raise RuntimeError(f"Local LLM request failed: {last_error}")

    if not summary or not summary.strip():
        raise RuntimeError("The model returned an empty response")
    return summary.strip()


def generate_summary_with_settings(
    candidate_text: str,
    settings: LocalLLMSettings | None = None,
    assessment_prompt: str = ASSESSMENT_PROMPT,
    job_role: str = DEFAULT_JOB_ROLE,
) -> str:
    settings = settings or LocalLLMSettings()
    return generate_summary(
        settings.base_url,
        settings.api_key,
        settings.model,
        candidate_text,
        settings.max_tokens,
        assessment_prompt=assessment_prompt,
        job_role=job_role,
        timeout=settings.timeout,
        max_retries=settings.max_retries,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input_dir",
        nargs="?",
        type=Path,
        default=Path("candidate_split"),
        help="Directory containing one .txt file per candidate",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--api-key",
        default=None,
        help="LLM server API key (prefer the LLM_API_KEY environment variable)",
    )
    parser.add_argument("--data-source-id", default=DEFAULT_DATA_SOURCE_ID)
    parser.add_argument("--max-tokens", type=int, default=1400)
    parser.add_argument("--delay", type=float, default=0.0, help="Seconds between LLM calls")
    parser.add_argument(
        "--candidate",
        help="Process only this candidate name (the filename without .txt)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate summaries and print them without writing to Notion",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input_dir.is_dir():
        print(f"Input directory not found: {args.input_dir}", file=sys.stderr)
        return 2

    candidate_files = sorted(args.input_dir.glob("*.txt"), key=lambda p: p.name.casefold())
    if args.candidate:
        wanted = normalize_name(args.candidate)
        candidate_files = [p for p in candidate_files if normalize_name(p.stem) == wanted]
    if not candidate_files:
        print("No matching candidate .txt files found", file=sys.stderr)
        return 2

    # OPENAI_API_KEY is supported as a fallback for compatibility with the SDK.
    llm_api_key = (
        args.api_key
        or os.environ.get("LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or "12345"
    )
    llm_settings = LocalLLMSettings(
        base_url=args.base_url,
        model=args.model,
        api_key=llm_api_key,
        max_tokens=args.max_tokens,
        delay=args.delay,
    )

    notion: NotionHelper | None = None
    data = None
    if not args.dry_run:
        notion_token = os.environ.get("NOTION_TOKEN")
        if not notion_token:
            print("NOTION_TOKEN must be set unless --dry-run is used", file=sys.stderr)
            return 2
        notion = NotionHelper(notion_token=notion_token, max_retries=3)
        data = notion.get_data_source_pages_as_dataframe(
            args.data_source_id,
            include_page_ids=True,
        )
        required_columns = {"Fullname", "notion_page_id"}
        missing_columns = required_columns.difference(data.columns)
        if missing_columns:
            print(
                "Notion DataFrame is missing columns: "
                + ", ".join(sorted(missing_columns)),
                file=sys.stderr,
            )
            return 1

        missing = [
            path.stem
            for path in candidate_files
            if data[data["Fullname"] == path.stem].empty
        ]
        if missing:
            print(
                "No exact Notion page-title match for: " + ", ".join(missing),
                file=sys.stderr,
            )
            print("No LLM calls or Notion writes were made.", file=sys.stderr)
            return 1

    failures = 0
    for position, path in enumerate(candidate_files, start=1):
        candidate_name = path.stem
        print(f"[{position}/{len(candidate_files)}] {candidate_name}")
        try:
            page_id: str | None = None
            if not args.dry_run:
                assert data is not None
                the_row = data[data["Fullname"] == candidate_name]
                if len(the_row) != 1:
                    raise RuntimeError(
                        f"Expected one Notion row for {candidate_name!r}; found {len(the_row)}"
                    )
                page_id = str(the_row.iloc[0]["notion_page_id"]).strip()
                if not page_id or page_id.casefold() == "nan":
                    raise RuntimeError(f"Missing notion_page_id for {candidate_name!r}")

            candidate_text = path.read_text(encoding="utf-8-sig").strip()
            summary = generate_summary_with_settings(candidate_text, llm_settings)

            print(f"\n===== {candidate_name} =====\n")


            if args.dry_run:
                print("  Dry run: Notion was not updated")
            else:
                assert notion is not None
                assert page_id is not None

                # Re-read immediately before mutation so a concurrent Notion edit is
                # observed and existing page content is never replaced.
                notion.get_page(page_id, return_markdown=True)
                raw_markdown = f"### Candidate\n\n{summary}"
                notion.append_page_body(
                    page_id,
                    body=raw_markdown,
                )
                print(f"  Appended to Notion page: {candidate_name} ({page_id})")
        except Exception as exc:
            failures += 1
            print(f"  ERROR: {exc}", file=sys.stderr)

        if args.delay > 0 and position < len(candidate_files):
            time.sleep(args.delay)

    succeeded = len(candidate_files) - failures
    print(f"Finished: {succeeded} succeeded, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
