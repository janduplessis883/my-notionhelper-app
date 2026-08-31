"""Streamlit page for converting PDFs to rendered Markdown with Marker."""

from pathlib import Path
import re
import tempfile
from typing import Any

import streamlit as st
from notionhelper import NotionHelper


def _safe_file_stem(filename: str) -> str:
    stem = Path(filename or "uploaded-pdf").stem
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-_")
    return stem or "uploaded-pdf"


@st.cache_resource(show_spinner=False)
def _load_marker_converter() -> Any:
    """Load Marker once per Streamlit process because its models are expensive."""
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
    except ImportError as exc:
        raise RuntimeError(
            "Marker is not installed. Install project dependencies with "
            "`pip install -r requirements.txt`."
        ) from exc

    return PdfConverter(artifact_dict=create_model_dict())


def convert_pdf_to_markdown(pdf_bytes: bytes, filename: str) -> str:
    """Convert uploaded PDF bytes to Markdown using Marker."""
    with tempfile.TemporaryDirectory(prefix="marker-pdf-") as temp_dir:
        pdf_path = Path(temp_dir) / f"{_safe_file_stem(filename)}.pdf"
        pdf_path.write_bytes(pdf_bytes)
        rendered = _load_marker_converter()(str(pdf_path))
        markdown = getattr(rendered, "markdown", None)

    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("Marker did not return any Markdown for this PDF.")
    return markdown


def render_marker_pdf_to_markdown(nh: NotionHelper) -> None:
    st.caption("Marker, PDF to Markdown")
    st.subheader(":material/description: Convert PDF to Markdown")
    st.markdown(
        "Upload a PDF and Marker will extract its text and structure into Markdown. "
        "The result below is rendered so you can review it before downloading."
    )

    uploaded_pdf = st.file_uploader(
        "Upload PDF",
        type=["pdf"],
        accept_multiple_files=False,
        key="marker_pdf_to_markdown_upload",
    )

    if uploaded_pdf is None:
        st.info("Upload a PDF to begin.")
        return

    upload_signature = (uploaded_pdf.name, uploaded_pdf.size)
    if st.session_state.get("marker_upload_signature") != upload_signature:
        st.session_state.marker_upload_signature = upload_signature
        st.session_state.marker_markdown = None

    if st.button(
        "Convert to Markdown",
        type="primary",
        icon=":material/auto_awesome:",
        width="stretch",
    ):
        with st.spinner("Marker is converting the PDF...", show_time=True):
            try:
                st.session_state.marker_markdown = convert_pdf_to_markdown(
                    uploaded_pdf.getvalue(), uploaded_pdf.name
                )
            except Exception as exc:
                st.session_state.marker_markdown = None
                st.error(f":material/error: Failed to convert PDF: {exc}")

    markdown = st.session_state.get("marker_markdown")
    if not markdown:
        return

    st.success(":material/check_circle: Markdown created successfully.")
    with st.expander("Rendered Markdown", icon=":material/preview:", expanded=True):
        st.markdown(markdown)

    notion_url = st.text_input(
        "Notion page URL",
        placeholder="Paste the Notion page URL where the Markdown should be appended...",
        key="marker_notion_page_url",
        help="The page must be shared with the Notion integration used by this app.",
    )
    page_id = None
    if notion_url:
        try:
            page_id = nh.extract_page_id_from_url(notion_url)
            st.info(f":material/info: Destination page ID: `{page_id}`")
        except Exception as exc:
            st.error(f":material/error: Could not extract a Notion page ID: {exc}")

    if st.button(
        "Append Markdown to Notion",
        type="secondary",
        icon=":material/note_add:",
        width="stretch",
    ):
        if not page_id:
            st.error(":material/error: Enter a valid Notion page URL first.")
        else:
            with st.spinner("Appending Markdown to Notion...", show_time=True):
                try:
                    nh.append_page_body(page_id, body=markdown)
                except Exception as exc:
                    st.error(f":material/error: Failed to append Markdown to Notion: {exc}")
                else:
                    st.success(
                        f":material/check_circle: Markdown appended to Notion page `{page_id}`."
                    )

    st.download_button(
        "Download Markdown file",
        data=markdown.encode("utf-8"),
        file_name=f"{_safe_file_stem(uploaded_pdf.name)}.md",
        mime="text/markdown",
        icon=":material/download:",
        width="stretch",
    )
