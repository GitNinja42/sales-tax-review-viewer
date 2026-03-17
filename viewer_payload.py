#!/usr/bin/env python3

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, time
from functools import lru_cache
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from run_utils import load_run_manifest
from workbook_utils import choose_review_sheet, extract_transaction_rows


CONTROL_LIBRARY = "sales-tax-control-library.json"
DISPLAY_HEADERS = [
    "Date",
    "Transaction Type",
    "#",
    "Adj",
    "Name",
    "Location",
    "Class",
    "Memo/Description",
    "Account",
    "Tax Amount",
    "Net Amount",
    "Gross Total",
    "Balance",
    "Tax Code",
]

LEGACY_STATUS_MAP = {"Likely Incorrect": "Review Needed"}


def json_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def canonicalize_status(value: Any) -> str:
    status = str(value or "").strip()
    return LEGACY_STATUS_MAP.get(status, status)


@lru_cache(maxsize=1)
def load_control_map(base_dir: str) -> dict[str, dict[str, Any]]:
    path = Path(base_dir) / CONTROL_LIBRARY
    payload = json.loads(path.read_text(encoding="utf-8"))
    controls = payload.get("controls") if isinstance(payload, dict) else payload
    control_map: dict[str, dict[str, Any]] = {}
    for item in controls:
        control_id = str(item.get("control_id") or item.get("id") or "").strip()
        if not control_id:
            continue
        control_map[control_id] = {
            "controlId": control_id,
            "title": item.get("title", control_id),
            "area": item.get("area"),
            "level": item.get("level"),
            "reviewQuestion": item.get("review_question"),
            "defaultStatus": item.get("default_status"),
            "evidenceFields": item.get("evidence_fields", []),
            "missingContext": item.get("missing_context", []),
        }
    return control_map


def workbook_path_for_run(run_dir: Path, manifest: dict[str, object], base_dir: Path | None = None) -> Path:
    candidates = [manifest.get("source_workbook"), manifest.get("reviewed_workbook"), manifest.get("default_reviewed_workbook")]
    for raw in candidates:
        if not raw:
            continue
        path = Path(str(raw))
        if path.exists():
            return path
        # Try resolving relative paths against base_dir.
        if base_dir and not path.is_absolute():
            resolved = base_dir / path
            if resolved.exists():
                return resolved
        # Try resolving against run_dir.
        resolved = run_dir / path.name
        if resolved.exists():
            return resolved

    # Last resort: look for any xlsx in run_dir or inputs/.
    for pattern in ["inputs/*.xlsx", "*.xlsx"]:
        matches = list(run_dir.glob(pattern))
        if matches:
            return matches[0]

    raise FileNotFoundError(f"No workbook found for run: {run_dir}")


def load_annotations(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "annotations.json"
    if not path.exists():
        return {"row_annotations": [], "pattern_annotations": [], "unmapped_observations": []}
    return json.loads(path.read_text(encoding="utf-8"))


def checklist_titles(checklist_refs: list[str], control_map: dict[str, dict[str, Any]]) -> list[str]:
    return [str(control_map.get(ref, {}).get("title") or ref) for ref in checklist_refs]


def row_values_payload(row: dict[str, object]) -> dict[str, Any]:
    values: dict[str, Any] = {"Section": json_scalar(row.get("section"))}
    raw = dict(row.get("raw") or {})
    for header in DISPLAY_HEADERS:
        values[header] = json_scalar(raw.get(header))
    return values


def build_viewer_payload(base_dir: Path, run_dir: Path, run_summary: dict[str, Any]) -> dict[str, Any]:
    manifest = load_run_manifest(run_dir)
    workbook_path = workbook_path_for_run(run_dir, manifest, base_dir=base_dir)
    workbook = load_workbook(workbook_path, data_only=True)
    ws, header_row, _ = choose_review_sheet(workbook)
    _, transaction_rows = extract_transaction_rows(ws, header_row)

    annotations = load_annotations(run_dir)
    control_map = load_control_map(str(base_dir))

    annotation_map: dict[int, dict[str, Any]] = {}
    checklist_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()

    for item in annotations.get("row_annotations", []):
        row_num = int(item["source_row"])
        refs = [str(ref) for ref in item.get("checklist_refs", [])]
        status = canonicalize_status(item.get("status"))
        if status:
            status_counter[status] += 1
        checklist_counter.update(refs)
        annotation_map[row_num] = {
            "status": status or None,
            "issueSummary": item.get("issue_summary"),
            "checklistRefs": refs,
            "checklistTitles": checklist_titles(refs, control_map),
            "missingContext": list(item.get("missing_context", [])),
            "suggestedNextStep": item.get("suggested_next_step"),
            "highlightColumns": list(item.get("highlight_columns", [])),
            "_dismissed": bool(item.get("_dismissed", False)),
        }

    pattern_rows: dict[int, list[str]] = defaultdict(list)
    patterns: list[dict[str, Any]] = []
    for item in annotations.get("pattern_annotations", []):
        refs = [str(ref) for ref in item.get("checklist_refs", [])]
        row_refs = [int(value) for value in item.get("row_refs", [])]
        pattern_id = str(item.get("pattern_id"))
        for row_ref in row_refs:
            pattern_rows[row_ref].append(pattern_id)
        patterns.append(
            {
                "patternId": pattern_id,
                "issueSummary": item.get("issue_summary"),
                "checklistRefs": refs,
                "checklistTitles": checklist_titles(refs, control_map),
                "rowRefs": row_refs,
                "missingContext": list(item.get("missing_context", [])),
            }
        )

    rows_payload: list[dict[str, Any]] = []
    flagged_rows = 0
    for row in transaction_rows:
        row_num = int(row["row_num"])
        annotation = annotation_map.get(row_num)
        if annotation:
            flagged_rows += 1
        rows_payload.append(
            {
                "rowNum": row_num,
                "section": json_scalar(row.get("section")),
                "normalizedName": json_scalar(row.get("normalized_name")),
                "name": json_scalar(row.get("name")),
                "account": json_scalar(row.get("account")),
                "transactionType": json_scalar(row.get("transaction_type")),
                "transactionNumber": json_scalar(row.get("transaction_number")),
                "taxCode": json_scalar(row.get("tax_code")),
                "memoDescription": json_scalar(row.get("memo_description")),
                "taxAmount": json_scalar(row.get("tax_amount")),
                "netAmount": json_scalar(row.get("net_amount")),
                "impliedRate": json_scalar(row.get("implied_rate")),
                "isFlagged": annotation is not None,
                "annotation": annotation,
                "patternIds": pattern_rows.get(row_num, []),
                "values": row_values_payload(row),
            }
        )

    checklist_summary = [
        {
            "checklistRef": ref,
            "title": str(control_map.get(ref, {}).get("title") or ref),
            "count": count,
        }
        for ref, count in checklist_counter.most_common()
    ]

    return {
        "run": {
            **run_summary,
            "viewerWorkbook": workbook_path.name,
            "sheetName": ws.title,
            "headerRow": header_row,
        },
        "summary": {
            "transactionRows": len(transaction_rows),
            "flaggedRows": flagged_rows,
            "patternCount": len(patterns),
            "statusCounts": dict(status_counter),
            "checklistCounts": checklist_summary,
        },
        "controls": control_map,
        "patterns": patterns,
        "headers": ["Section", *DISPLAY_HEADERS],
        "rows": rows_payload,
        "unmappedObservations": list(annotations.get("unmapped_observations", [])),
    }
