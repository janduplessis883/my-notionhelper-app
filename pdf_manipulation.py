from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import streamlit as st
from streamlit.errors import StreamlitAPIException


PDF_COMPONENT_NAME = "streamlit-pdf.pdf_viewer"


def _ensure_streamlit_pdf_registered() -> None:
    try:
        from streamlit.components.v2.get_bidi_component_manager import get_bidi_component_manager

        manager = get_bidi_component_manager()
        if manager.get_component_asset_root(PDF_COMPONENT_NAME) is None:
            manager.discover_and_register_components(start_file_watching=False)
    except Exception:
        pass


def _preview_uploaded_pdf(uploaded_pdf) -> None:
    try:
        _ensure_streamlit_pdf_registered()
        st.pdf(uploaded_pdf, height=650, key="pdf_manipulation_preview")
    except StreamlitAPIException as exc:
        st.warning(f"PDF preview is unavailable in this environment: {exc}")


def _safe_pdf_name(filename: str, suffix: str) -> str:
    stem = (filename or "uploaded.pdf").rsplit(".", 1)[0].strip() or "uploaded"
    return f"{stem}-{suffix}.pdf"


def _get_pdf_reader(pdf_bytes: bytes, password: str | None = None):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required. Install dependencies with `pip install -r requirements.txt`.") from exc

    reader = PdfReader(BytesIO(pdf_bytes))
    if reader.is_encrypted:
        if not password:
            raise ValueError("This PDF is password protected. Enter the current PDF password.")
        if reader.decrypt(password) == 0:
            raise ValueError("The current PDF password did not unlock the file.")
    return reader


def _split_pdf_to_zip(pdf_bytes: bytes, filename: str, password: str | None = None) -> tuple[bytes, int]:
    try:
        from pypdf import PdfWriter
    except ImportError as exc:
        raise RuntimeError("pypdf is required. Install dependencies with `pip install -r requirements.txt`.") from exc

    reader = _get_pdf_reader(pdf_bytes, password=password)
    zip_buffer = BytesIO()

    with ZipFile(zip_buffer, "w", compression=ZIP_DEFLATED) as zip_file:
        for page_index, page in enumerate(reader.pages, start=1):
            writer = PdfWriter()
            writer.add_page(page)

            page_buffer = BytesIO()
            writer.write(page_buffer)
            zip_file.writestr(_safe_pdf_name(filename, f"page-{page_index:03d}"), page_buffer.getvalue())

    return zip_buffer.getvalue(), len(reader.pages)


def _encrypt_pdf(pdf_bytes: bytes, password: str, current_password: str | None = None) -> bytes:
    try:
        from pypdf import PdfWriter
    except ImportError as exc:
        raise RuntimeError("pypdf is required. Install dependencies with `pip install -r requirements.txt`.") from exc

    reader = _get_pdf_reader(pdf_bytes, password=current_password)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password=password)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def render_pdf_manipulation() -> None:
    st.caption("PDF Manipulation")
    st.subheader(":material/picture_as_pdf: PDF Manipulation")

    uploaded_pdf = st.file_uploader(
        "Upload PDF",
        type=["pdf"],
        accept_multiple_files=False,
        key="pdf_manipulation_upload",
    )

    if uploaded_pdf is None:
        st.info("Upload a PDF to preview and manipulate it.")
        return

    pdf_bytes = uploaded_pdf.getvalue()
    _preview_uploaded_pdf(uploaded_pdf)

    current_password = st.text_input(
        "Current PDF password",
        type="password",
        key="pdf_manipulation_current_password",
        help="Only needed if the uploaded PDF is already password protected.",
    )

    action = st.tabs(["Split PDF", "Add Password"])

    with action[0]:
        st.markdown("Split the uploaded PDF into one PDF file per page.")
        if st.button("Split PDF", type="primary", icon=":material/call_split:", width="stretch"):
            with st.spinner("Splitting PDF...", show_time=True):
                try:
                    zip_bytes, page_count = _split_pdf_to_zip(
                        pdf_bytes,
                        uploaded_pdf.name,
                        password=current_password or None,
                    )
                except Exception as exc:
                    st.error(f":material/error: Failed to split PDF: {exc}")
                    return

            st.success(f":material/check_circle: Split {page_count} page(s).")
            st.download_button(
                "Download split PDFs",
                data=zip_bytes,
                file_name=_safe_pdf_name(uploaded_pdf.name, "split-pages").replace(".pdf", ".zip"),
                mime="application/zip",
                icon=":material/download:",
                width="stretch",
            )

    with action[1]:
        st.markdown("Create a password-protected copy of the uploaded PDF.")
        new_password = st.text_input(
            "New PDF password",
            type="password",
            key="pdf_manipulation_new_password",
        )
        confirm_password = st.text_input(
            "Confirm new password",
            type="password",
            key="pdf_manipulation_confirm_password",
        )

        if st.button("Add Password", type="primary", icon=":material/lock:", width="stretch"):
            if not new_password:
                st.error(":material/error: Enter a new password.")
                return
            if new_password != confirm_password:
                st.error(":material/error: Passwords do not match.")
                return

            with st.spinner("Encrypting PDF...", show_time=True):
                try:
                    encrypted_bytes = _encrypt_pdf(
                        pdf_bytes,
                        new_password,
                        current_password=current_password or None,
                    )
                except Exception as exc:
                    st.error(f":material/error: Failed to add password: {exc}")
                    return

            st.success(":material/check_circle: Password-protected PDF created.")
            st.download_button(
                "Download password-protected PDF",
                data=encrypted_bytes,
                file_name=_safe_pdf_name(uploaded_pdf.name, "password-protected"),
                mime="application/pdf",
                icon=":material/download:",
                width="stretch",
            )
