#!/usr/bin/env python3
"""Classify unlinked agenda items and relate them to Stanhope Projects."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any, Dict, Iterable, Iterator, Optional, Sequence, Tuple

from notionhelper import (
    AuthError,
    NotFoundError,
    NotionAPIError,
    NotionHelper,
    RateLimitError,
    RetryPolicy,
    TimeoutError,
    ValidationError,
)
from typesafe_sdk import AsyncTypeSafeClient, Choice


NOTION_API_BASE_URL = "https://api.notion.com/v1"
DATABASE_IDS = (
    "21cfdfd6-8a97-801e-afbe-000bbceea6f9",
    "203fdfd6-8a97-80a1-861a-000b951a59bf",
)
DEFAULT_MODEL = "jev-latest"
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.70
DEFAULT_AGENDA_PROP = "Agenda Item"

PROJECT_CRITERIA: Dict[str, str] = {
    "Neighbourhood Health Framework": "Neighbourhood health delivery, integrated local care, population health, or the neighbourhood health framework.",
    "AI Automation": "Artificial intelligence, automated workflows, AI tools, or AI-enabled service improvement.",
    "ECS Partnership & Merger": "ECS partnership work, merger activity, due diligence, governance, or integration planning.",
    "Questions?": "Unresolved general questions, decisions, or requests for clarification that do not clearly fit another project.",
    "Finance": "Budgets, invoices, payments, financial reporting, funding, or other financial management.",
    "Clinical Governance": "Clinical quality, patient safety, audit, risk, policy, incidents, or clinical governance processes.",
    "Nursing & HCA Supervision": "Supervision, support, training, workload, or management of nurses and healthcare assistants.",
    "Covid-19 & Flu Vaccination": "COVID-19 or influenza vaccination clinics, campaigns, delivery, eligibility, stock, or uptake.",
    "CRM - Cardiac Renal Metabolic": "Cardiac, renal, metabolic, hypertension, diabetes, or CRM care and improvement work.",
    "Python": "Python software, scripts, programming, data processing, or technical automation specifically involving Python.",
    "Complaints": "Patient complaints, responses, investigation, learning, or complaint handling.",
    "Brompton Health PCN": "Brompton Health Primary Care Network matters, PCN delivery, or PCN-specific coordination.",
    "Meetings": "Meeting planning, agendas, minutes, attendance, actions, or general meeting coordination.",
    "Human Resources": "Recruitment, employment, staff relations, contracts, leave, appraisal, or HR policy.",
    "Clinical Pharmacists": "Clinical pharmacist roles, medicines optimisation, pharmacist workload, or pharmacist-led services.",
    "Friends and Family Test": "Friends and Family Test collection, analysis, reporting, feedback, or service-improvement actions.",
    "NHS app": "NHS App adoption, support, access, features, patient communications, or related digital services.",
    "Cervical Screening": "Cervical screening invitations, clinics, uptake, recalls, results, or screening improvement.",
    "Management Activity": "General operational management, planning, coordination, reporting, or leadership that fits no more specific project.",
    "PPG": "Patient Participation Group activity, engagement, meetings, feedback, or PPG communications.",
    "Access DES": "Access DES requirements, appointment access, capacity, service standards, or related delivery work.",
}


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def _plain_text(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        plain = item.get("plain_text")
        if isinstance(plain, str) and plain:
            parts.append(plain)
            continue
        content = item.get("text", {}).get("content") if isinstance(item.get("text"), dict) else None
        if isinstance(content, str) and content:
            parts.append(content)
    return "".join(parts).strip()


def _property_text(page: Dict[str, Any], property_name: str) -> str:
    prop = page.get("properties", {}).get(property_name)
    if not isinstance(prop, dict):
        return ""
    property_type = prop.get("type")
    if property_type == "title":
        return _plain_text(prop.get("title"))
    if property_type == "rich_text":
        return _plain_text(prop.get("rich_text"))
    return ""


def _title_property_name(schema: Dict[str, Any]) -> str:
    for name, prop in (schema.get("properties") or {}).items():
        if isinstance(prop, dict) and prop.get("type") == "title":
            return str(name)
    raise RuntimeError("The Projects data source has no title property.")


def _require_property_type(schema: Dict[str, Any], property_name: str, allowed_types: Tuple[str, ...]) -> None:
    prop = (schema.get("properties") or {}).get(property_name)
    if not isinstance(prop, dict):
        available = sorted(str(name) for name in (schema.get("properties") or {}).keys())
        suffix = f" Available properties: {', '.join(available)}." if available else ""
        raise RuntimeError(f"Notion property not found: {property_name}.{suffix}")
    if prop.get("type") not in allowed_types:
        raise RuntimeError(
            f"Notion property '{property_name}' must be one of {', '.join(allowed_types)}; "
            f"found {prop.get('type')!r}."
        )


def _get_data_source_id(helper: NotionHelper, database_or_data_source_id: str) -> str:
    try:
        database = helper.get_database(database_or_data_source_id)
    except NotionAPIError:
        schema = helper.get_data_source(database_or_data_source_id)
        if schema.get("object") != "data_source":
            raise
        return database_or_data_source_id

    data_sources = database.get("data_sources") or []
    if not data_sources or not isinstance(data_sources[0], dict):
        raise RuntimeError("The Agenda Items database has no data source.")
    data_source_id = data_sources[0].get("id")
    if not isinstance(data_source_id, str) or not data_source_id:
        raise RuntimeError("Could not read the Agenda Items data source ID.")
    return data_source_id


def _relation_target_data_source_id(helper: NotionHelper, schema: Dict[str, Any], property_name: str) -> str:
    prop = (schema.get("properties") or {}).get(property_name)
    if not isinstance(prop, dict) or prop.get("type") != "relation":
        raise RuntimeError(f"Notion property '{property_name}' must be a relation property.")
    relation = prop.get("relation") or {}
    if not isinstance(relation, dict):
        raise RuntimeError(f"Notion relation '{property_name}' has an invalid configuration.")

    data_source_id = relation.get("data_source_id")
    if isinstance(data_source_id, str) and data_source_id:
        return data_source_id
    database_id = relation.get("database_id")
    if isinstance(database_id, str) and database_id:
        return _get_data_source_id(helper, database_id)
    raise RuntimeError(f"Could not determine the target data source for relation '{property_name}'.")


def _query_data_source(
    helper: NotionHelper,
    data_source_id: str,
    *,
    filter_obj: Optional[Dict[str, Any]] = None,
    limit: Optional[int] = None,
) -> Iterator[Dict[str, Any]]:
    url = f"{NOTION_API_BASE_URL}/data_sources/{data_source_id}/query"
    cursor: Optional[str] = None
    count = 0
    while True:
        payload: Dict[str, Any] = {"page_size": 100}
        if filter_obj is not None:
            payload["filter"] = filter_obj
        if cursor:
            payload["start_cursor"] = cursor
        response = helper._make_request("POST", url, payload=payload)
        for page in response.get("results") or []:
            if not isinstance(page, dict):
                continue
            yield page
            count += 1
            if limit is not None and count >= limit:
                return
        if not response.get("has_more") or not response.get("next_cursor"):
            return
        cursor = str(response["next_cursor"])


def _project_page_ids(helper: NotionHelper, data_source_id: str) -> Dict[str, str]:
    schema = helper.get_data_source(data_source_id)
    title_property = _title_property_name(schema)
    by_name: Dict[str, str] = {}
    # Use NotionHelper's supported data-source iterator here.  In particular,
    # this keeps retrieval compatible with the 2025-09-03 database/data-source
    # split and gives us the actual related row page IDs needed by PATCH.
    for page in helper.iter_data_source_pages(data_source_id, page_size=100):
        page_id = page.get("id")
        name = _property_text(page, title_property)
        if isinstance(page_id, str) and name in PROJECT_CRITERIA:
            by_name[name] = page_id
    missing = [name for name in PROJECT_CRITERIA if name not in by_name]
    if missing:
        raise RuntimeError("Projects data source is missing these project pages: " + ", ".join(missing))
    return by_name


def _build_agenda_state(title: str, description: str) -> str:
    return f"Agenda item: {title}\n\nBrief description: {description}"


def _jev_evaluate(
    *,
    model: str,
    state: str,
    timeout_s: float,
    max_retries: int,
) -> Dict[str, Any]:
    async def evaluate() -> Dict[str, Any]:
        async with AsyncTypeSafeClient(api_key=_env("TYPESAFE_API_KEY"), model=model, timeout=timeout_s) as client:
            response = await client.system_one(
                state={"document": state},
                questions={
                    "project": Choice(
                        instructions=(
                    "Choose the primary Stanhope Project for this agenda item. Choose exactly one project. "
                    "Use Questions? only when the item is genuinely an unresolved general question and no specific "
                    "project fits. Prefer a specific project over Management Activity or Meetings."
                ),
                        criteria=PROJECT_CRITERIA,
                    )
                },
            )
            answer = response.choices["project"]
            return {"choice": answer.choice, "confidence": answer.confidence, "probabilities": answer.probabilities}

    return asyncio.run(evaluate())


def _project_answer(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise RuntimeError("Malformed Jev response: missing project answer.")
    choice = raw.get("choice")
    if choice not in PROJECT_CRITERIA:
        raise RuntimeError(f"Malformed Jev response: invalid project choice {choice!r}.")
    return raw


def _choose_relation_project_names(
    answer: Dict[str, Any], valid_projects: Sequence[str], low_confidence_threshold: float
) -> Tuple[str, ...]:
    choice = answer.get("choice")
    if choice not in valid_projects:
        raise RuntimeError(f"Unexpected Jev project choice: {choice!r}")
    confidence = answer.get("confidence")
    probabilities = answer.get("probabilities")
    if not isinstance(confidence, (int, float)) and isinstance(probabilities, dict):
        confidence = probabilities.get(choice)
    confidence = float(confidence) if isinstance(confidence, (int, float)) else 0.0
    if confidence >= low_confidence_threshold:
        return (str(choice),)

    scores = probabilities if isinstance(probabilities, dict) else {}
    ranked = sorted(
        ((name, float(score)) for name, score in scores.items() if name in valid_projects and isinstance(score, (int, float))),
        key=lambda item: item[1],
        reverse=True,
    )
    names = [name for name, _score in ranked]
    if choice not in names:
        names.insert(0, str(choice))
    if len(names) < 2:
        raise RuntimeError("Low-confidence Jev response lacks a second valid project score.")
    return tuple(names[:2])


def _relation_property_value(page_ids: Sequence[str]) -> Dict[str, Any]:
    return {"relation": [{"id": page_id} for page_id in page_ids]}


def _update_relation(helper: NotionHelper, page_id: str, property_name: str, project_page_ids: Sequence[str]) -> None:
    helper._make_request(
        "PATCH",
        f"{NOTION_API_BASE_URL}/pages/{page_id}",
        payload={"properties": {property_name: _relation_property_value(project_page_ids)}},
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Classify Agenda Items into Stanhope Projects with Jev.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--agenda-prop", default=DEFAULT_AGENDA_PROP)
    parser.add_argument("--description-prop", default="Brief Description")
    parser.add_argument("--relation-prop", default="Stanhope Projects")
    parser.add_argument("--low-confidence-threshold", type=float, default=DEFAULT_LOW_CONFIDENCE_THRESHOLD)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--max-retries", type=int, default=2)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not 0 <= args.low_confidence_threshold <= 1:
        parser.error("--low-confidence-threshold must be between 0 and 1.")

    try:
        helper = NotionHelper(
            notion_token=_env("NOTION_TOKEN"),
            retry_policy=RetryPolicy(max_retries=5, base_delay=0.5, max_delay=15.0, jitter_ratio=0.2, timeout=30.0),
        )
        _env("TYPESAFE_API_KEY")
    except (AuthError, NotFoundError, NotionAPIError, RuntimeError) as err:
        print(f"Setup error: {err}", file=sys.stderr)
        return 2

    scored = skipped = errors = 0
    empty_relation_filter = {"property": args.relation_prop, "relation": {"is_empty": True}}
    for database_id in DATABASE_IDS:
        print(f"\nClassifying database {database_id}")
        try:
            data_source_id = _get_data_source_id(helper, database_id)
            schema = helper.get_data_source(data_source_id)
            _require_property_type(schema, args.agenda_prop, ("title", "rich_text"))
            _require_property_type(schema, args.description_prop, ("rich_text",))
            _require_property_type(schema, args.relation_prop, ("relation",))
            project_page_ids = _project_page_ids(
                helper, _relation_target_data_source_id(helper, schema, args.relation_prop)
            )
        except (AuthError, NotFoundError, NotionAPIError, RuntimeError) as err:
            errors += 1
            print(f"[error] Could not set up database {database_id}: {err}", file=sys.stderr)
            continue

        try:
            for page in _query_data_source(helper, data_source_id, filter_obj=empty_relation_filter, limit=args.limit):
                page_id = page.get("id")
                if not isinstance(page_id, str):
                    continue
                title = _property_text(page, args.agenda_prop)
                description = _property_text(page, args.description_prop)
                if not title and not description:
                    skipped += 1
                    continue
                try:
                    raw = _jev_evaluate(
                        model=args.model,
                        state=_build_agenda_state(title, description),
                        timeout_s=args.timeout,
                        max_retries=args.max_retries,
                    )
                    names = _choose_relation_project_names(
                        _project_answer(raw), tuple(PROJECT_CRITERIA), args.low_confidence_threshold
                    )
                    relation_ids = tuple(project_page_ids[name] for name in names)
                    if args.dry_run:
                        print(f"[dry-run] {title or description} -> {', '.join(names)}")
                    else:
                        _update_relation(helper, page_id, args.relation_prop, relation_ids)
                        print(f"{title or description} -> {', '.join(names)}")
                    scored += 1
                except Exception as err:
                    errors += 1
                    print(f"[error] Could not classify page_id={page_id} title={title!r}: {err}", file=sys.stderr)
        except NotionAPIError as err:
            errors += 1
            print(f"[error] Could not query database {database_id}: {err}", file=sys.stderr)

    print(f"\nDone. scored={scored} skipped={skipped} errors={errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
