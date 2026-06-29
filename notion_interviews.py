from pathlib import Path

import pandas as pd
from notionhelper import NotionHelper

CSV_PATH = Path("data/A4718-26-0002-contact-details.csv")
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
    "Phone": {"phone_number": {}},
    "Email": {"email": {}},
    "Interview Date": {"date": {}},
}


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


def render_notion_interview_database(nh: NotionHelper) -> None:
    """Render the Streamlit UI for creating and populating the interview database."""

    import streamlit as st

    st.caption("Notion Interview Database")
    st.markdown("Create an interview scoring database and import candidate contact details.")

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
