"""Streamlit page for generating structured meeting notes."""

from dataclasses import dataclass
import re
from typing import Callable

from notion_blockify import Blockizer
import streamlit as st

from llm_client import FREELLM, LLMConfig, build_llm_config
from meeting_notes_agent import format_notes, generate_meeting_notes
from meeting_transcript import decode_transcript_upload


@dataclass(frozen=True)
class GeneratedMeetingNotes:
    transcript: str
    markdown: str
    download_filename: str


def build_meeting_llm_config(api_key: str) -> LLMConfig:
    """Meeting notes always use the fixed FreeLLM provider and model."""
    if not api_key:
        raise ValueError("FREELLMAPI_API_KEY is missing from Streamlit secrets.")
    return build_llm_config(FREELLM, api_key)


def _download_filename(title: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return f"{stem or 'meeting_notes'}.md"


def process_meeting_upload(
    filename: str | None,
    payload: bytes | None,
    api_key: str,
    generation_fn=generate_meeting_notes,
) -> GeneratedMeetingNotes:
    """Validate an upload, generate notes, and prepare a download payload."""
    if not filename or payload is None:
        raise ValueError("Please upload a .txt or .vtt transcript.")
    transcript = decode_transcript_upload(filename, payload)
    config = build_meeting_llm_config(api_key)
    notes = generation_fn(transcript, config)
    markdown = format_notes(notes)
    return GeneratedMeetingNotes(
        transcript=transcript,
        markdown=markdown,
        download_filename=_download_filename(notes.get("meeting_title", "Meeting Notes")),
    )


def _extract_notion_page_id(notion_url: str) -> str | None:
    uuid_match = re.search(
        r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
        notion_url,
        re.IGNORECASE,
    )
    if uuid_match:
        return uuid_match.group(0).lower()
    compact_match = re.search(r"[a-f0-9]{32}", notion_url, re.IGNORECASE)
    if not compact_match:
        return None
    compact = compact_match.group(0).lower()
    return (
        f"{compact[:8]}-{compact[8:12]}-{compact[12:16]}-"
        f"{compact[16:20]}-{compact[20:]}"
    )


def append_meeting_notes_to_notion(
    notion_url: str,
    markdown: str,
    notion_helper,
    blockizer=None,
) -> str:
    """Append generated meeting-note Markdown to a Notion page body."""
    if not notion_url.strip():
        raise ValueError("Enter a Notion page URL before appending notes.")
    page_id = _extract_notion_page_id(notion_url)
    if not page_id:
        raise ValueError("Enter a valid Notion page URL.")
    if not markdown.strip():
        raise ValueError("There are no meeting notes to append.")

    converter = blockizer or Blockizer()
    blocks = converter.convert(markdown)
    if not blocks:
        raise ValueError("The meeting notes did not produce any valid Notion blocks.")
    for index in range(0, len(blocks), 100):
        notion_helper.append_page_body(page_id, blocks=blocks[index : index + 100])
    return page_id


def render_meeting_notes_page(
    api_key: str,
    append_to_notion: Callable[[str, str], str],
) -> None:
    """Render transcript upload, generation, download, and Notion append UI."""
    st.subheader(":material/clinical_notes: Meeting Notes Agent")
    st.caption("Upload a text or WebVTT transcript. Meeting notes use FreeLLM model `auto`.")

    if not api_key:
        st.error("FREELLMAPI_API_KEY is missing from Streamlit secrets.")

    uploaded = st.file_uploader(
        "Meeting transcript",
        type=["txt", "vtt"],
        help="WebVTT timestamps and speaker labels are retained.",
        key="meeting_notes_upload",
    )

    preview_error = None
    if uploaded is not None:
        try:
            transcript = decode_transcript_upload(uploaded.name, uploaded.getvalue())
            with st.expander("Transcript preview", expanded=False):
                st.code(transcript, language="text", wrap_lines=True)
        except ValueError as exc:
            preview_error = str(exc)
            st.error(preview_error)

    if st.button(
        "Generate meeting notes",
        type="primary",
        icon=":material/auto_awesome:",
        disabled=uploaded is None or not api_key or preview_error is not None,
    ):
        try:
            with st.spinner("Generating meeting notes...", show_time=True):
                result = process_meeting_upload(
                    uploaded.name,
                    uploaded.getvalue(),
                    api_key,
                )
            st.session_state["meeting_notes_markdown"] = result.markdown
            st.session_state["meeting_notes_download_filename"] = result.download_filename
        except Exception as exc:
            st.error(f"Could not generate meeting notes: {exc}")

    markdown = st.session_state.get("meeting_notes_markdown", "")
    if not markdown:
        return

    st.markdown("### Generated notes")
    with st.container(border=True):
        st.markdown(markdown)

    st.download_button(
        "Download Markdown",
        data=markdown,
        file_name=st.session_state.get(
            "meeting_notes_download_filename",
            "meeting_notes.md",
        ),
        mime="text/markdown",
        icon=":material/download:",
    )

    st.divider()
    notion_url = st.text_input(
        "Notion page URL (optional)",
        placeholder="https://www.notion.so/...",
        key="meeting_notes_notion_url",
    )
    if st.button(
        "Append to Notion page",
        icon=":material/note_add:",
        disabled=not notion_url.strip(),
    ):
        try:
            with st.spinner("Appending notes to Notion...", show_time=True):
                page_id = append_to_notion(notion_url, markdown)
            st.success(f"Meeting notes appended to Notion page `{page_id}`.")
        except Exception as exc:
            st.error(f"Could not append meeting notes to Notion: {exc}")
