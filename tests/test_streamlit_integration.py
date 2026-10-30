import pytest

from llm_client import FREELLM, GROQ, build_llm_config


def test_provider_routing_selects_groq_key_and_model():
    from llm_client import select_llm_config

    config = select_llm_config(
        GROQ,
        groq_api_key="groq-secret",
        freellm_api_key="free-secret",
        groq_model="qwen/qwen3-32b",
    )

    assert config == build_llm_config(GROQ, "groq-secret", "qwen/qwen3-32b")


def test_provider_routing_selects_freellm_key_and_auto_model():
    from llm_client import select_llm_config

    config = select_llm_config(
        FREELLM,
        groq_api_key="groq-secret",
        freellm_api_key="free-secret",
        groq_model="ignored",
    )

    assert config == build_llm_config(FREELLM, "free-secret")


def test_provider_routing_rejects_missing_selected_key():
    from llm_client import select_llm_config

    with pytest.raises(ValueError, match="FREELLMAPI_API_KEY"):
        select_llm_config(
            FREELLM,
            groq_api_key="groq-secret",
            freellm_api_key="",
            groq_model="ignored",
        )


def test_notion_provider_routing_uses_injected_config():
    from razor_db_create_new_page import generate_llm_markdown

    config = build_llm_config(FREELLM, "free-secret")
    captured = {}

    def completion(config_arg, prompt):
        captured.update(config=config_arg, prompt=prompt)
        return "# Generated"

    assert generate_llm_markdown(config, "Write this", completion) == "# Generated"
    assert captured == {"config": config, "prompt": "Write this"}


def test_meeting_notes_routing_is_always_freellm_auto():
    from meeting_notes_page import build_meeting_llm_config

    config = build_meeting_llm_config("meeting-secret")

    assert config.provider == FREELLM
    assert config.model == "auto"
    assert config.api_key == "meeting-secret"


def test_meeting_notes_page_processes_upload_and_builds_safe_download():
    from meeting_notes_page import process_meeting_upload

    def generate(transcript, config):
        assert transcript == "Sarah: Hello"
        assert config.provider == FREELLM
        return {
            "meeting_title": "Roadmap / Q4 Review!",
            "participants": ["Sarah"],
            "summary": "Hello",
        }

    result = process_meeting_upload(
        "meeting.txt",
        b"Sarah: Hello",
        "meeting-secret",
        generation_fn=generate,
        narrative_generation_fn=lambda transcript, config, notes: "### Context\n- Hello",
    )

    assert result.transcript == "Sarah: Hello"
    assert result.markdown.startswith("# Roadmap / Q4 Review!")
    assert "## Narrative Summary\n### Context\n- Hello\n\n## Summary" in result.markdown
    assert result.download_filename == "roadmap_q4_review.md"


def test_meeting_notes_page_rejects_missing_file():
    from meeting_notes_page import process_meeting_upload

    with pytest.raises(ValueError, match="upload"):
        process_meeting_upload(None, None, "meeting-secret")


def test_meeting_notes_page_decode_error_prevents_generation():
    from meeting_notes_page import process_meeting_upload

    calls = []

    def generate(*args):
        calls.append(args)

    with pytest.raises(ValueError, match="UTF-8"):
        process_meeting_upload(
            "meeting.txt",
            b"\xff",
            "meeting-secret",
            generation_fn=generate,
        )

    assert calls == []


@pytest.mark.parametrize(
    ("url", "markdown", "error"),
    [
        ("", "# Notes", "Notion page URL"),
        ("https://www.notion.so/not-a-page", "# Notes", "valid Notion page"),
        ("https://www.notion.so/Test-0123456789abcdef0123456789abcdef", "", "notes to append"),
    ],
)
def test_meeting_notes_page_append_validates_input(url, markdown, error):
    from meeting_notes_page import append_meeting_notes_to_notion

    with pytest.raises(ValueError, match=error):
        append_meeting_notes_to_notion(url, markdown, object())


def test_meeting_notes_page_append_batches_blocks_in_hundreds():
    from meeting_notes_page import append_meeting_notes_to_notion

    class FakeBlockizer:
        def convert(self, markdown):
            assert markdown == "# Notes"
            return [{"type": "paragraph", "n": n} for n in range(205)]

    class FakeNotionHelper:
        def __init__(self):
            self.calls = []

        def append_page_body(self, page_id, blocks):
            self.calls.append((page_id, blocks))

    notion = FakeNotionHelper()
    page_id = append_meeting_notes_to_notion(
        "https://www.notion.so/Test-0123456789abcdef0123456789abcdef",
        "# Notes",
        notion,
        blockizer=FakeBlockizer(),
    )

    assert page_id == "01234567-89ab-cdef-0123-456789abcdef"
    assert [len(blocks) for _, blocks in notion.calls] == [100, 100, 5]
    assert {call_page_id for call_page_id, _ in notion.calls} == {page_id}


def test_meeting_notes_page_upload_identity_changes_with_file_content():
    from meeting_notes_page import upload_identity

    first = upload_identity("meeting.txt", b"Sarah: First meeting")
    renamed = upload_identity("renamed.txt", b"Sarah: First meeting")
    changed = upload_identity("meeting.txt", b"Sarah: Different meeting")

    assert first != renamed
    assert first != changed
    assert first == upload_identity("meeting.txt", b"Sarah: First meeting")
