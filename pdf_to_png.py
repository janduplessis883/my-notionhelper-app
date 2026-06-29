from datetime import datetime
from pathlib import Path
import re
from typing import Any

import streamlit as st
from streamlit.errors import StreamlitAPIException
from notionhelper import NotionHelper


DATA_PATH = Path("pdf-images")
PDF_COMPONENT_NAME = "streamlit-pdf.pdf_viewer"


def _safe_file_stem(filename: str) -> str:
    stem = Path(filename or "uploaded-pdf").stem.lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return stem or "uploaded-pdf"


def convert_pdf_to_pngs(uploaded_pdf: Any, dpi: int = 200) -> list[Path]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF is required for PDF conversion. Install project dependencies with `pip install -r requirements.txt`."
        ) from exc

    DATA_PATH.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_stem = _safe_file_stem(getattr(uploaded_pdf, "name", "uploaded-pdf"))
    pdf_bytes = uploaded_pdf.getvalue()
    png_paths: list[Path] = []
    document = fitz.open(stream=pdf_bytes, filetype="pdf")

    try:
        if document.page_count == 0:
            raise ValueError("The uploaded PDF does not contain any pages.")

        scale = dpi / 72
        matrix = fitz.Matrix(scale, scale)
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            output_path = DATA_PATH / f"{file_stem}-{timestamp}-page-{page_index + 1:03d}.png"
            pixmap.save(output_path)
            png_paths.append(output_path)
    finally:
        document.close()

    return png_paths


def upload_pngs_to_notion(nh: NotionHelper, page_id: str, png_paths: list[Path]) -> list[dict[str, Any]]:
    responses = []
    for png_path in png_paths:
        response = nh.one_step_image_embed(page_id, str(png_path))
        if isinstance(response, dict) and response.get("object") == "error":
            message = response.get("message", "Notion returned an error while embedding the image.")
            raise RuntimeError(message)
        responses.append(response)
    return responses


def _ensure_streamlit_pdf_registered() -> None:
    try:
        from streamlit.components.v2.get_bidi_component_manager import get_bidi_component_manager

        manager = get_bidi_component_manager()
        if manager.get_component_asset_root(PDF_COMPONENT_NAME) is None:
            manager.discover_and_register_components(start_file_watching=False)
    except Exception:
        pass


def _preview_uploaded_pdf(uploaded_pdf: Any) -> None:
    try:
        _ensure_streamlit_pdf_registered()
        st.pdf(uploaded_pdf, height=650, key="pdf_to_png_preview")
    except StreamlitAPIException as exc:
        st.warning(f"PDF preview is unavailable in this environment: {exc}")


def render_pdf_to_png(nh: NotionHelper) -> None:
    st.caption("PDF to PNG")
    st.subheader(":material/picture_as_pdf: PDF to PNG")

    notion_url = st.text_input(
        "Notion Page URL",
        placeholder="Paste the Notion page URL here...",
        key="pdf_to_png_notion_url",
    )
    uploaded_pdf = st.file_uploader(
        "Upload PDF",
        type=["pdf"],
        accept_multiple_files=False,
        key="pdf_to_png_upload",
    )
    if uploaded_pdf is not None:
        _preview_uploaded_pdf(uploaded_pdf)

    dpi = st.slider(
        "Image quality",
        min_value=120,
        max_value=300,
        value=200,
        step=20,
        help="Higher values create sharper PNGs, but upload larger files to Notion.",
    )

    page_id = None
    if notion_url:
        try:
            page_id = nh.extract_page_id_from_url(notion_url)
            st.info(f":material/info: Extracted Page ID: `{page_id}`")
        except Exception as exc:
            st.error(f":material/error: Could not extract a Notion page ID: {exc}")

    if st.button("Convert and Save to Notion", type="primary", icon=":material/upload_file:", width="stretch"):
        if not uploaded_pdf:
            st.error(":material/error: Please upload a PDF.")
            return
        if not page_id:
            st.error(":material/error: Please enter a valid Notion page URL.")
            return

        with st.spinner("Converting PDF pages and uploading PNGs to Notion...", show_time=True):
            try:
                png_paths = convert_pdf_to_pngs(uploaded_pdf, dpi=dpi)
                upload_pngs_to_notion(nh, page_id, png_paths)
            except Exception as exc:
                st.error(f":material/error: Failed to save PDF images to Notion: {exc}")
                return

        st.success(f":material/check_circle: Saved {len(png_paths)} PNG image(s) to Notion page `{page_id}`.")
        with st.expander("Converted PNG Preview", icon=":material/image:", expanded=True):
            for png_path in png_paths:
                st.image(str(png_path), caption=png_path.name, width="stretch")
