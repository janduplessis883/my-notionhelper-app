import json

import pytest

from llm_client import build_llm_config
from meeting_notes_agent import (
    NARRATIVE_SUMMARY_PROMPT,
    NOTES_PROMPT,
    format_notes,
    generate_narrative_summary,
    generate_meeting_notes,
    normalize_notion_checkboxes,
    parse_json_response,
)


NOTES = {
    "meeting_title": "Roadmap Review",
    "date": "2026-10-27",
    "participants": ["Sarah", "John"],
    "duration_estimate": "30 minutes",
    "summary": "The team reviewed the roadmap.",
    "key_decisions": ["Freeze on 15 November"],
    "action_items": [
        {"task": "Escalate PaymentCo", "owner": "John", "due": "Today"}
    ],
    "discussion_topics": ["Q4 roadmap", "Payment integration"],
    "blockers": ["Payment API documentation"],
    "next_meeting": "2026-11-03 10:00",
    "follow_up_questions": ["When will PaymentCo respond?"],
}


def test_parse_json_response_accepts_fence_and_surrounding_text():
    payload = json.dumps(NOTES)

    assert parse_json_response(f"Result follows:\n```json\n{payload}\n```\nDone") == NOTES


def test_parse_json_response_rejects_malformed_json():
    with pytest.raises(ValueError, match="valid JSON"):
        parse_json_response("```json\n{not json}\n```")


def test_generate_meeting_notes_uses_supplied_config_and_prompt():
    config = build_llm_config("FreeLLM", "secret")
    captured = {}

    def completion(config_arg, prompt, system_prompt=None):
        captured.update(
            config=config_arg,
            prompt=prompt,
            system_prompt=system_prompt,
        )
        return json.dumps(NOTES)

    result = generate_meeting_notes(
        "[00:01 --> 00:02] Sarah: Hello",
        config,
        completion_fn=completion,
    )

    assert result == NOTES
    assert captured == {
        "config": config,
        "prompt": "Meeting transcript:\n\n[00:01 --> 00:02] Sarah: Hello",
        "system_prompt": NOTES_PROMPT,
    }


def test_generate_meeting_notes_rejects_empty_transcript():
    config = build_llm_config("FreeLLM", "secret")

    with pytest.raises(ValueError, match="empty"):
        generate_meeting_notes("  ", config)


def test_generate_narrative_summary_uses_transcript_and_structured_notes():
    config = build_llm_config("FreeLLM", "secret")
    captured = {}

    def completion(config_arg, prompt, system_prompt=None):
        captured.update(
            config=config_arg,
            prompt=prompt,
            system_prompt=system_prompt,
        )
        return json.dumps({"narrative_summary": "### Context\n- The team aligned on the release."})

    result = generate_narrative_summary(
        "Sarah: We discussed the release.",
        config,
        NOTES,
        completion_fn=completion,
    )

    assert result == "### Context\n- The team aligned on the release."
    assert captured == {
        "config": config,
        "prompt": (
            "Meeting transcript:\n\nSarah: We discussed the release.\n\n"
            "Structured notes:\n\n"
            f"{json.dumps(NOTES, ensure_ascii=False)}"
        ),
        "system_prompt": NARRATIVE_SUMMARY_PROMPT,
    }


def test_format_notes_includes_all_structured_sections():
    markdown = format_notes(NOTES)

    assert "# Roadmap Review" in markdown
    assert "**Participants:** Sarah, John" in markdown
    assert "## Summary\nThe team reviewed the roadmap." in markdown
    assert "## Key Decisions\n- Freeze on 15 November" in markdown
    assert "**Escalate PaymentCo** — Owner: John | Due: Today" in markdown
    assert "## Discussion Topics\n- Q4 roadmap\n- Payment integration" in markdown
    assert "## Blockers\n- Payment API documentation" in markdown
    assert "**Next Meeting:** 2026-11-03 10:00" in markdown
    assert "## Follow-up Questions\n- When will PaymentCo respond?" in markdown


def test_format_notes_places_narrative_summary_before_existing_summary():
    notes = {
        **NOTES,
        "narrative_summary": "### Context\n- The team needed three weeks for QA.\n\n### Decision rationale\n- The freeze protects the release date.",
    }

    markdown = format_notes(notes)

    assert markdown.index("## Narrative Summary") < markdown.index("## Summary")
    assert "## Narrative Summary\n### Context\n- The team needed three weeks for QA." in markdown


def test_normalize_notion_checkboxes_removes_leading_list_marker():
    markdown = """## Action Items
- [ ] Coordinate with Siamma
  - [ ] Confirm the meeting time
- Ordinary bullet
"""

    assert normalize_notion_checkboxes(markdown) == """## Action Items
[ ] Coordinate with Siamma
  [ ] Confirm the meeting time
- Ordinary bullet
"""


def test_format_notes_uses_notion_checkbox_syntax():
    markdown = format_notes(NOTES)

    assert "[ ] **Escalate PaymentCo**" in markdown
    assert "- [ ]" not in markdown
