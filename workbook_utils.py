#!/usr/bin/env python3

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


REQUIRED_HEADERS = {"Date", "Transaction Type", "Tax Code"}
PREFERRED_HEADERS = [
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
REVIEW_HEADERS = {
    "Review Status",
    "Issue Summary",
    "Checklist Ref(s)",
    "Missing Context",
    "Suggested Next Step",
}
TRAILING_ENTITY_WORDS = {
    "company",
    "co",
    "inc",
    "corp",
    "corporation",
    "llc",
    "ltd",
    "limited",
}


def find_default_workbook(base_dir: Path) -> Path:
    candidate_dirs = [base_dir / "review-inputs", base_dir]
    workbooks = []
    for directory in candidate_dirs:
        if not directory.exists():
            continue
        for path in directory.glob("*.xlsx"):
            if path.name.startswith("~$"):
                continue
            if "review-output" in path.parts:
                continue
            workbooks.append(path)
    if not workbooks:
        raise FileNotFoundError("No .xlsx workbook found in the folder root or review-inputs.")
    if len(workbooks) > 1:
        names = ", ".join(path.name for path in workbooks)
        raise FileExistsError(f"Multiple .xlsx files found in the folder root or review-inputs: {names}")
    return workbooks[0]


def find_header_row(ws) -> int | None:
    for row_num in range(1, min(ws.max_row, 25) + 1):
        values = [ws.cell(row_num, col).value for col in range(1, ws.max_column + 1)]
        value_set = {value for value in values if value}
        if REQUIRED_HEADERS.issubset(value_set):
            return row_num
    return None


def sheet_inventory(wb) -> list[dict[str, object]]:
    inventory = []
    for ws in wb.worksheets:
        header_row = find_header_row(ws)
        headers = []
        if header_row is not None:
            headers = [ws.cell(header_row, col).value for col in range(1, ws.max_column + 1)]
        inventory.append(
            {
                "sheet_name": ws.title,
                "header_row": header_row,
                "max_row": ws.max_row,
                "max_column": ws.max_column,
                "headers": headers,
                "contains_review_columns": bool(REVIEW_HEADERS.intersection({header for header in headers if header})),
            }
        )
    return inventory


def workbook_review_artifacts(wb) -> list[str]:
    inventory = sheet_inventory(wb)
    reasons: list[str] = []
    if any(bool(item["contains_review_columns"]) for item in inventory):
        reasons.append("review columns are already present on a workbook sheet")
    if any("pattern flags" == str(item["sheet_name"]).strip().lower() for item in inventory):
        reasons.append("a Pattern Flags sheet is already present")
    if any("reviewed" in str(item["sheet_name"]).strip().lower() for item in inventory):
        reasons.append("a reviewed worksheet is already present")
    return reasons


def choose_review_sheet(wb) -> tuple[object, int, list[dict[str, object]]]:
    candidates = []
    inventory = sheet_inventory(wb)
    for item in inventory:
        header_row = item["header_row"]
        if header_row is None:
            continue
        ws = wb[item["sheet_name"]]
        headers = item["headers"]
        preferred_matches = sum(1 for header in headers if header in PREFERRED_HEADERS)
        title_penalty = 0
        lowered_title = ws.title.lower()
        if "review" in lowered_title:
            title_penalty += 5
        if item["contains_review_columns"]:
            title_penalty += 10
        data_rows = max(ws.max_row - header_row, 0)
        score = (preferred_matches * 100) + min(data_rows, 1000) - title_penalty
        candidates.append((score, data_rows, -title_penalty, ws.title))

    if not candidates:
        raise ValueError("Could not find a worksheet with the required sales-tax headers.")

    best_title = sorted(candidates, reverse=True)[0][3]
    best_item = next(item for item in inventory if item["sheet_name"] == best_title)
    return wb[best_title], int(best_item["header_row"]), inventory


def normalize_client_name(name: str) -> str:
    root = name.split(":")[0].strip()
    root = re.sub(r"\s*\[[^\]]+\]", "", root).strip()
    root = re.sub(r"\s+", " ", root)
    words = root.split()
    while words and words[-1].lower().rstrip(".") in TRAILING_ENTITY_WORDS:
        words.pop()
    return " ".join(words).strip()


def extract_transaction_rows(ws, header_row: int) -> tuple[list[str], list[dict[str, object]]]:
    headers = [ws.cell(header_row, col).value for col in range(1, ws.max_column + 1)]
    section = ""
    rows = []

    for row_num in range(header_row + 1, ws.max_row + 1):
        values = [ws.cell(row_num, col).value for col in range(1, ws.max_column + 1)]
        col_a = values[0]
        col_b = values[1] if len(values) > 1 else None

        if isinstance(col_a, str) and col_a.startswith("Total for "):
            continue
        if col_a and col_b is None:
            section = str(col_a)
            continue
        if col_b is None:
            continue

        row = dict(zip(headers, values))
        tax_amount = float(row.get("Tax Amount") or 0)
        net_amount = float(row.get("Net Amount") or 0)
        implied_rate = None
        if net_amount:
            implied_rate = round(abs(tax_amount / net_amount), 6)
        rows.append(
            {
                "row_num": row_num,
                "section": section,
                "date": row.get("Date"),
                "transaction_type": row.get("Transaction Type"),
                "transaction_number": row.get("#"),
                "adj": row.get("Adj"),
                "name": row.get("Name"),
                "normalized_name": normalize_client_name(str(row.get("Name") or "")) if row.get("Name") else "",
                "location": row.get("Location"),
                "class": row.get("Class"),
                "memo_description": row.get("Memo/Description"),
                "account": row.get("Account"),
                "tax_amount": tax_amount,
                "net_amount": net_amount,
                "gross_total": row.get("Gross Total"),
                "balance": row.get("Balance"),
                "tax_code": row.get("Tax Code"),
                "implied_rate": implied_rate,
                "raw": row,
            }
        )

    return headers, rows


def count_values(rows: list[dict[str, object]], key: str, limit: int | None = None) -> list[tuple[str, int]]:
    counter = Counter(str(row.get(key) or "") for row in rows if row.get(key) not in (None, ""))
    if limit is None:
        return counter.most_common()
    return counter.most_common(limit)
