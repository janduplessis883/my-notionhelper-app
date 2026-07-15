from pathlib import Path
import re

import fitz
import pandas as pd
import streamlit as st
from notionhelper import NotionHelper
from split_candidates import CandidateRecord, split_candidate_records
from summarize_candidates_to_notion import (
    ASSESSMENT_PROMPT,
    DEFAULT_BASE_URL,
    DEFAULT_JOB_ROLE,
    DEFAULT_MODEL,
    LocalLLMSettings,
    generate_summary_with_settings,
    normalize_name,
)

CSV_PATH = Path("example_data/A4718-26-0003-contact-details.csv")
PDF_PATH = Path("example_data/A4718-26-0003-Application forms.Pdf")
DEFAULT_PARENT_PAGE_URL = (
    "https://app.notion.com/p/janduplessis/"
    "Human-Resources-205fdfd68a97803e9ea8ce7955f9f562?source=copy_link"
)

DATABASE_NAME = "HCA_Recruit_July26"
DEFAULT_NUMBER_FIELDS = [
    "Conflict Resolution",
    "Communication",
    "Clinical Skill",
    "Qualification",
    "Confidentiality",
    "Adaptability",
]

BASE_DATABASE_PROPERTIES = {
    "Application Reference": {"title": {}},
    "First Name": {"rich_text": {}},
    "Surname": {"rich_text": {}},
    "Outcome Emailed": {"checkbox": {}},
    "Notes": {"rich_text": {}},
    "Candidate Summary": {"checkbox": {}},
    "LLM Score": {"number": {"format": "number"}},
    "Phone": {"phone_number": {}},
    "Email": {"email": {}},
    "Interview Date": {"date": {}},
}

NOTION_API_BASE = "https://api.notion.com/v1"
SUMMARY_PROPERTY = "Candidate Summary"
LLM_SCORE_PROPERTY = "LLM Score"


def normalise_number_field_name(field_name: str) -> str:
    return " ".join(field_name.strip().split())


def parse_extra_number_fields(raw_fields: str) -> list[str]:
    fields = raw_fields.replace(",", "\n").splitlines()
    return [
        normalise_number_field_name(field)
        for field in fields
        if normalise_number_field_name(field)
    ]


def unique_field_names(field_names: list[str]) -> list[str]:
    unique_names = []
    seen_names = set()
    for field_name in field_names:
        comparable_name = field_name.casefold()
        if comparable_name not in seen_names:
            unique_names.append(field_name)
            seen_names.add(comparable_name)
    return unique_names


def build_total_score_formula(number_fields: list[str]) -> str:
    if not number_fields:
        return "0"

    formula_parts = [
        f'prop("{field_name.replace("\"", "\\\"")}")'
        for field_name in number_fields
    ]
    return f'({" + ".join(formula_parts)}).toNumber()'


def build_database_properties(number_fields: list[str] | None = None) -> dict:
    properties = BASE_DATABASE_PROPERTIES.copy()
    selected_number_fields = unique_field_names(number_fields or DEFAULT_NUMBER_FIELDS)

    for field_name in selected_number_fields:
        properties[field_name] = {"number": {"format": "number"}}

    return properties


DATABASE_PROPERTIES = build_database_properties()


def create_notion_database(
    nh: NotionHelper,
    parent_page_id: str,
    database_name: str = DATABASE_NAME,
    number_fields: list[str] | None = None,
) -> str:
    """Create the Notion database and return the data source ID."""

    response = nh.create_database(
        parent_page_id,
        database_name,
        build_database_properties(number_fields),
    )

    return response["data_sources"][0]["id"]


def build_properties(row) -> dict:
    """Convert one CSV row into Notion page properties."""

    return {
        "Application Reference": {
            "title": [
                {
                    "text": {
                        "content": str(row.Application_reference)
                    }
                }
            ]
        },
        "First Name": {
            "rich_text": [
                {
                    "text": {
                        "content": str(row.First_name)
                    }
                }
            ]
        },
        "Surname": {
            "rich_text": [
                {
                    "text": {
                        "content": str(row.Surname)
                    }
                }
            ]
        },
        "Phone": {
            "phone_number": str(row.Phone)
        },
        "Email": {
            "email": str(row.Email)
        },
    }


def normalise_contact_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise common CSV column names used by the interview export."""

    df = df.copy()
    df.columns = df.columns.str.strip()
    df.columns = (
        df.columns
        .str.replace(" ", "_", regex=False)
        .str.replace("-", "_", regex=False)
    )
    df.rename(
        columns={
            "Last_name": "Surname",
            "Telephone_number": "Phone",
            "Email_address": "Email",
        },
        inplace=True,
    )
    return df


def validate_contact_columns(df: pd.DataFrame) -> None:
    required_columns = ["Application_reference", "First_name", "Surname", "Phone", "Email"]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing_columns)}")


def load_contact_csv(csv_source) -> pd.DataFrame:
    df = pd.read_csv(csv_source)
    df = normalise_contact_columns(df)
    validate_contact_columns(df)
    return df


def process_csv(
    nh: NotionHelper,
    database_id: str,
    csv_path: Path = CSV_PATH,
) -> int:

    df = load_contact_csv(csv_path)
    for row in df.itertuples(index=False):
        nh.new_page_to_data_source(
            database_id,
            build_properties(row),
        )

        print(f"Added {row.Application_reference}")

    return len(df)


def process_dataframe(
    nh: NotionHelper,
    database_id: str,
    df: pd.DataFrame,
) -> int:
    df = normalise_contact_columns(df)
    validate_contact_columns(df)

    for row in df.itertuples(index=False):
        nh.new_page_to_data_source(
            database_id,
            build_properties(row),
        )

    return len(df)


def extract_pdf_text(pdf_source) -> str:
    """Extract plain text from an uploaded PDF or local PDF path in memory."""

    if isinstance(pdf_source, (str, Path)):
        doc = fitz.open(pdf_source)
    else:
        doc = fitz.open(stream=pdf_source.getvalue(), filetype="pdf")

    try:
        return "\n".join(page.get_text("text") for page in doc).strip()
    finally:
        doc.close()


def extract_llm_score(summary: str) -> float:
    patterns = [
        r"Suitability score:\s*(\d+(?:\.\d+)?)\s*/\s*10",
        r"score:\s*(\d+(?:\.\d+)?)\s*/\s*10",
        r"(\d+(?:\.\d+)?)\s*/\s*10",
    ]
    for pattern in patterns:
        match = re.search(pattern, summary, re.IGNORECASE)
        if match:
            score = float(match.group(1))
            if 0 <= score <= 10:
                return score
            raise ValueError(f"LLM score must be between 0 and 10; got {score:g}.")
    raise ValueError("Could not find an LLM suitability score out of 10 in the summary.")


def update_candidate_completion_properties(nh: NotionHelper, page_id: str, llm_score: float) -> None:
    nh._make_request(
        "PATCH",
        f"{NOTION_API_BASE}/pages/{page_id}",
        payload={
            "properties": {
                SUMMARY_PROPERTY: {"checkbox": True},
                LLM_SCORE_PROPERTY: {"number": llm_score},
            }
        },
    )


def row_value(row: pd.Series, *columns: str) -> str:
    for column in columns:
        if column in row.index and pd.notna(row[column]):
            value = str(row[column]).strip()
            if value and value.casefold() != "nan":
                return value
    return ""


def notion_candidate_index(nh: NotionHelper, data_source_id: str) -> tuple[dict[str, dict], dict[str, dict]]:
    data = nh.get_data_source_pages_as_dataframe(data_source_id, include_page_ids=True)
    if "notion_page_id" not in data.columns:
        raise ValueError("Notion rows did not include notion_page_id.")

    by_reference: dict[str, dict] = {}
    by_name: dict[str, dict] = {}

    for _, row in data.iterrows():
        first_name = row_value(row, "First Name", "First_name")
        surname = row_value(row, "Surname", "Last Name", "Last_name")
        full_name = row_value(row, "Fullname", "Name") or f"{first_name} {surname}".strip()
        reference = row_value(row, "Application Reference", "Application_reference")
        page_id = row_value(row, "notion_page_id")

        if not page_id:
            continue

        candidate = {
            "name": full_name,
            "reference": reference.upper(),
            "page_id": page_id,
        }
        if reference:
            by_reference[reference.upper()] = candidate
        if full_name:
            by_name[normalize_name(full_name)] = candidate

    return by_reference, by_name


def match_candidate(
    candidate: CandidateRecord,
    by_reference: dict[str, dict],
    by_name: dict[str, dict],
) -> dict:
    reference_match = by_reference.get(candidate.reference.upper())
    candidate_name = normalize_name(candidate.name)

    if reference_match:
        notion_name = normalize_name(reference_match["name"])
        if notion_name and notion_name != candidate_name:
            raise ValueError(
                f"Application reference matched {reference_match['reference']}, but PDF name "
                f"{candidate.name!r} does not match Notion name {reference_match['name']!r}."
            )
        return reference_match

    name_match = by_name.get(candidate_name)
    if name_match:
        return name_match

    raise ValueError(
        f"No matching Notion row found for {candidate.name} ({candidate.reference})."
    )


def append_candidate_summary(nh: NotionHelper, page_id: str, candidate: CandidateRecord, summary: str) -> None:
    llm_score = extract_llm_score(summary)
    markdown = (
        f"---\n\n"
        f"## Candidate Summary\n\n"
        f"**Application reference:** {candidate.reference}\n\n"
        f"{summary}"
    )
    nh.append_page_body(page_id, body=markdown)
    update_candidate_completion_properties(nh, page_id, llm_score)


def summarize_candidates_to_notion_pages(
    nh: NotionHelper,
    data_source_id: str,
    candidates: list[CandidateRecord],
    llm_settings: LocalLLMSettings,
    job_role: str,
    assessment_prompt: str,
    progress_bar,
) -> tuple[int, int]:
    by_reference, by_name = notion_candidate_index(nh, data_source_id)

    succeeded = 0
    failed = 0
    total = len(candidates)
    if total == 0:
        progress_bar.progress(1.0, text="No candidate records found.")
        return succeeded, failed

    for index, candidate in enumerate(candidates, start=1):
        progress_bar.progress((index - 1) / total, text=f"{index}/{total}: {candidate.name}")

        with st.status(
            f"{index}/{total}: {candidate.name} (`{candidate.reference}`)",
            state="running",
            expanded=True,
        ) as candidate_status:
            try:
                st.write("Matching candidate to Notion database row...")
                notion_candidate = match_candidate(candidate, by_reference, by_name)
                st.write(f"Matched Notion page `{notion_candidate['page_id']}`.")

                st.write("Calling local LLM...")
                summary = generate_summary_with_settings(
                    candidate.text,
                    llm_settings,
                    assessment_prompt=assessment_prompt,
                    job_role=job_role,
                )
                llm_score = extract_llm_score(summary)
                st.write(f"LLM score found: `{llm_score:g}/10`.")

                st.write("Appending summary to Notion page body...")
                append_candidate_summary(
                    nh,
                    notion_candidate["page_id"],
                    candidate,
                    summary,
                )
                succeeded += 1
                candidate_status.update(
                    label=(
                        f"{candidate.name}: wrote summary and set "
                        f"`{SUMMARY_PROPERTY}` / `{LLM_SCORE_PROPERTY}`"
                    ),
                    state="complete",
                    expanded=False,
                )
                st.success(
                    f"Wrote summary to Notion page for {candidate.name} "
                    f"(`{notion_candidate['page_id']}`), score `{llm_score:g}/10`."
                )
            except Exception as exc:
                failed += 1
                candidate_status.update(
                    label=f"{candidate.name}: failed",
                    state="error",
                    expanded=True,
                )
                st.error(f"Failed for {candidate.name}: {exc}")

    progress_bar.progress(1.0, text=f"Finished: {succeeded} succeeded, {failed} failed")
    return succeeded, failed


def render_notion_interview_database(nh: NotionHelper) -> None:
    """Render the Streamlit UI for creating and populating the interview database."""

    st.caption("Notion Interview Database")
    st.markdown("Create an interview scoring database and import candidate contact details.")
    st.warning(
        "This workflow must be run locally on your host machine so it can reach the local LLM endpoint.",
        icon=":material/computer:",
    )

    parent_page_url = st.text_input(
        "Parent Notion page URL",
        value=DEFAULT_PARENT_PAGE_URL,
        help="The new interview database will be created inside this Notion page.",
    )
    database_name = st.text_input("Database name", value=DATABASE_NAME)

    st.subheader("Number fields")
    selected_number_fields = []
    for field_name in DEFAULT_NUMBER_FIELDS:
        include_field = st.checkbox(
            field_name,
            value=True,
            key=f"interview_number_field_{field_name}",
        )
        if include_field:
            selected_number_fields.append(field_name)

    extra_number_fields = st.text_area(
        "Additional number fields",
        placeholder="Leadership\nTeamwork",
        help="Add one field per line, or separate fields with commas.",
    )
    selected_number_fields = unique_field_names(
        selected_number_fields + parse_extra_number_fields(extra_number_fields)
    )

    uploaded_csv = st.file_uploader(
        "Candidate contact CSV",
        type=["csv"],
        help="Expected columns include Application reference, First name, Last name, Telephone number, and Email address.",
    )
    uploaded_pdf = st.file_uploader(
        "Candidate experience, education and qualifications PDF",
        type=["pdf"],
        help="The PDF is converted to plain text in memory, split by candidate, summarized with your local LLM, and appended to each Notion candidate page.",
    )

    with st.expander("Local LLM settings", expanded=False):
        llm_base_url = st.text_input(
            "Endpoint",
            value=DEFAULT_BASE_URL,
            help="OpenAI-compatible local LLM endpoint root, for example http://127.0.0.1:8000/v1.",
        )
        llm_api_key = st.text_input(
            "API key",
            value="12345",
            help="Bearer token sent to your local LLM server.",
        )
        llm_model = st.text_input(
            "Model",
            value=DEFAULT_MODEL,
            help="Model name sent to your local LLM server.",
        )
        st.caption("Endpoint defaults come from `summarize_candidates_to_notion.py`.")

    with st.expander("Recruitment scoring prompt", expanded=True):
        job_role = st.text_input(
            "Job being recruited for",
            value=DEFAULT_JOB_ROLE,
            help="Describe the role, for example GP surgery practice nurse, practice manager, or GP surgery receptionist.",
        )
        assessment_prompt = st.text_area(
            "LLM scoring prompt",
            value=ASSESSMENT_PROMPT,
            height=460,
            help=(
                "Edit this for the role. Keep `{candidate_text}` where the application text should be inserted; "
                "`{job_role}` is replaced with the field above."
            ),
        )
        if "{candidate_text}" not in assessment_prompt:
            st.warning("The prompt must include `{candidate_text}` so the candidate application can be inserted.")

    if uploaded_csv is not None:
        try:
            preview_df = load_contact_csv(uploaded_csv)
            st.dataframe(preview_df.head(20), width="stretch", hide_index=True)
            st.info(f"Ready to import {len(preview_df)} candidate rows.")
        except Exception as exc:
            st.error(f"Could not read CSV: {exc}")
            preview_df = None
    elif CSV_PATH.exists():
        preview_df = load_contact_csv(CSV_PATH)
        st.info(f"Using default CSV: `{CSV_PATH}` ({len(preview_df)} rows).")
        st.dataframe(preview_df.head(20), width="stretch", hide_index=True)
    else:
        preview_df = None
        st.warning(f"Upload a CSV to import candidates. Default CSV not found at `{CSV_PATH}`.")

    pdf_source = None
    if uploaded_pdf is not None:
        pdf_source = uploaded_pdf
        st.info(f"Ready to extract candidate text from uploaded PDF: `{uploaded_pdf.name}`.")
    elif PDF_PATH.exists():
        pdf_source = PDF_PATH
        st.info(f"Using default PDF: `{PDF_PATH}`.")
    else:
        st.warning(f"Upload a PDF to summarize candidates. Default PDF not found at `{PDF_PATH}`.")

    create_database = st.button(
        "Create Interview Database",
        type="primary",
        icon=":material/database:",
        width="stretch",
    )

    if not create_database:
        return

    if not parent_page_url.strip():
        st.error("Please enter the parent Notion page URL.")
        return
    if pdf_source is not None and "{candidate_text}" not in assessment_prompt:
        st.error("Add `{candidate_text}` to the LLM scoring prompt before running summarization.")
        return

    try:
        parent_page_id = nh.extract_page_id_from_url(parent_page_url)
        data_source_id = create_notion_database(
            nh,
            parent_page_id,
            database_name.strip() or DATABASE_NAME,
            selected_number_fields,
        )
        st.success(f"Created Notion data source: `{data_source_id}`")

        if preview_df is not None:
            imported_count = process_dataframe(nh, data_source_id, preview_df)
            st.success(f"Imported {imported_count} candidates.")

            if pdf_source is not None:
                with st.spinner("Extracting and splitting candidate PDF...", show_time=True):
                    pdf_text = extract_pdf_text(pdf_source)
                    candidates = split_candidate_records(pdf_text)

                st.success(f"Extracted {len(candidates)} candidate records from the PDF.")
                progress_bar = st.progress(0, text="Starting local LLM summarization...")
                llm_settings = LocalLLMSettings(
                    base_url=llm_base_url.strip() or DEFAULT_BASE_URL,
                    model=llm_model.strip() or DEFAULT_MODEL,
                    api_key=llm_api_key.strip() or "12345",
                )
                succeeded, failed = summarize_candidates_to_notion_pages(
                    nh,
                    data_source_id,
                    candidates,
                    llm_settings,
                    job_role.strip() or DEFAULT_JOB_ROLE,
                    assessment_prompt,
                    progress_bar,
                )
                if failed:
                    st.warning(f"Candidate summarization finished with {failed} error(s).")
                else:
                    st.success(f"Candidate summarization finished: {succeeded} summaries written.")
            else:
                st.info("CSV imported. Upload a PDF if you also want candidate summaries.")
        else:
            st.info("Database created without candidate rows.")
    except Exception as exc:
        st.error(f"Failed to create interview database: {exc}")


def main():

    import streamlit as st

    nh = NotionHelper(st.secrets["NOTION_TOKEN"])

    parent_page_id = nh.extract_page_id_from_url(
        DEFAULT_PARENT_PAGE_URL
    )

    data_source_id = create_notion_database(
        nh,
        parent_page_id,
    )

    print(f"Created data source: {data_source_id}")

    process_csv(
        nh,
        data_source_id,
    )


if __name__ == "__main__":
    main()
