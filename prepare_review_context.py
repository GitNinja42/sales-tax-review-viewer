#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from run_utils import create_run_dir, write_run_manifest
from workbook_utils import choose_review_sheet, count_values, extract_transaction_rows, find_default_workbook


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare workbook context for an agent-led sales-tax checklist review.")
    parser.add_argument("--input-workbook", type=Path, default=None)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Existing or new run directory. Defaults to a new timestamped folder under review-output/runs/.",
    )
    parser.add_argument(
        "--run-label",
        type=str,
        default=None,
        help="Optional label to include in the run folder name instead of the workbook stem.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--include-row-dump",
        action="store_true",
        help="Also write workbook_rows.json. By default the pipeline stays xlsx-first and writes only lightweight helper context.",
    )
    return parser.parse_args()


def build_customer_profiles(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        key = str(row.get("normalized_name") or "").strip()
        if not key:
            continue
        item = grouped.setdefault(
            key,
            {
                "normalized_name": key,
                "display_names": set(),
                "tax_codes": defaultdict(int),
                "accounts": defaultdict(int),
                "transaction_types": defaultdict(int),
                "row_refs": [],
            },
        )
        if row.get("name"):
            item["display_names"].add(str(row["name"]))
        if row.get("tax_code"):
            item["tax_codes"][str(row["tax_code"])] += 1
        if row.get("account"):
            item["accounts"][str(row["account"])] += 1
        if row.get("transaction_type"):
            item["transaction_types"][str(row["transaction_type"])] += 1
        item["row_refs"].append(int(row["row_num"]))

    profiles = []
    for item in grouped.values():
        profiles.append(
            {
                "normalized_name": item["normalized_name"],
                "display_names": sorted(item["display_names"]),
                "tax_codes": dict(sorted(item["tax_codes"].items())),
                "accounts": dict(sorted(item["accounts"].items(), key=lambda pair: (-pair[1], pair[0]))),
                "transaction_types": dict(sorted(item["transaction_types"].items(), key=lambda pair: (-pair[1], pair[0]))),
                "row_refs": item["row_refs"],
                "has_multiple_tax_codes": len(item["tax_codes"]) > 1,
            }
        )
    profiles.sort(key=lambda item: (-len(item["row_refs"]), item["normalized_name"]))
    return profiles


def build_account_profiles(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        account = str(row.get("account") or "").strip()
        if not account:
            continue
        item = grouped.setdefault(
            account,
            {
                "account": account,
                "tax_codes": defaultdict(int),
                "transaction_types": defaultdict(int),
                "names": defaultdict(int),
                "row_refs": [],
            },
        )
        if row.get("tax_code"):
            item["tax_codes"][str(row["tax_code"])] += 1
        if row.get("transaction_type"):
            item["transaction_types"][str(row["transaction_type"])] += 1
        if row.get("normalized_name"):
            item["names"][str(row["normalized_name"])] += 1
        item["row_refs"].append(int(row["row_num"]))

    profiles = []
    for item in grouped.values():
        profiles.append(
            {
                "account": item["account"],
                "tax_codes": dict(sorted(item["tax_codes"].items())),
                "transaction_types": dict(sorted(item["transaction_types"].items(), key=lambda pair: (-pair[1], pair[0]))),
                "names": dict(sorted(item["names"].items(), key=lambda pair: (-pair[1], pair[0]))),
                "row_refs": item["row_refs"],
                "has_multiple_tax_codes": len(item["tax_codes"]) > 1,
            }
        )
    profiles.sort(key=lambda item: (-len(item["row_refs"]), item["account"]))
    return profiles


def build_rate_profiles(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        tax_code = str(row.get("tax_code") or "").strip()
        if not tax_code:
            continue
        item = grouped.setdefault(
            tax_code,
            {
                "tax_code": tax_code,
                "implied_rates": defaultdict(int),
                "row_refs": [],
            },
        )
        if row.get("implied_rate") is not None:
            item["implied_rates"][f"{float(row['implied_rate']):.6f}"] += 1
        item["row_refs"].append(int(row["row_num"]))

    profiles = []
    for item in grouped.values():
        profiles.append(
            {
                "tax_code": item["tax_code"],
                "implied_rates": dict(sorted(item["implied_rates"].items(), key=lambda pair: (-pair[1], pair[0]))),
                "row_refs": item["row_refs"],
            }
        )
    profiles.sort(key=lambda item: (-len(item["row_refs"]), item["tax_code"]))
    return profiles


def build_profile(
    workbook_path: Path,
    sheet_name: str,
    header_row: int,
    headers: list[str],
    rows: list[dict[str, object]],
    inventory: list[dict[str, object]],
    include_row_dump: bool,
) -> dict[str, object]:
    customer_profiles = build_customer_profiles(rows)
    account_profiles = build_account_profiles(rows)
    rate_profiles = build_rate_profiles(rows)
    sections = sorted({str(row["section"]) for row in rows if row.get("section")})

    return {
        "workbook_name": workbook_path.name,
        "selected_sheet": sheet_name,
        "header_row": header_row,
        "row_count": len(rows),
        "row_dump_generated": include_row_dump,
        "headers": headers,
        "sheet_inventory": inventory,
        "sections": sections,
        "counts": {
            "tax_codes": count_values(rows, "tax_code"),
            "transaction_types": count_values(rows, "transaction_type"),
            "accounts": count_values(rows, "account", limit=25),
        },
        "customer_tax_profiles": customer_profiles,
        "account_tax_profiles": account_profiles,
        "rate_profiles": rate_profiles,
    }


def build_summary(profile: dict[str, object]) -> str:
    lines = [
        "# Workbook Review Context",
        "",
        f"- workbook: `{profile['workbook_name']}`",
        f"- selected sheet: `{profile['selected_sheet']}`",
        f"- transaction rows extracted: `{profile['row_count']}`",
        f"- header row: `{profile['header_row']}`",
        f"- workbook remains source of truth: `yes`",
        f"- full row dump generated: `{profile['row_dump_generated']}`",
        "",
        "## Tax Codes",
    ]
    for tax_code, count in profile["counts"]["tax_codes"]:
        lines.append(f"- `{tax_code}`: {count}")

    lines.extend(["", "## Transaction Types"])
    for transaction_type, count in profile["counts"]["transaction_types"]:
        lines.append(f"- `{transaction_type}`: {count}")

    lines.extend(["", "## Top Accounts"])
    for account, count in profile["counts"]["accounts"][:10]:
        lines.append(f"- `{account}`: {count}")

    mixed_customers = [item for item in profile["customer_tax_profiles"] if item["has_multiple_tax_codes"]]
    lines.extend(["", "## Mixed-Tax Customers"])
    if mixed_customers:
        for item in mixed_customers[:20]:
            codes = ", ".join(sorted(item["tax_codes"].keys()))
            lines.append(f"- `{item['normalized_name']}`: {codes}")
    else:
        lines.append("- none detected from normalized names")

    mixed_accounts = [item for item in profile["account_tax_profiles"] if item["has_multiple_tax_codes"]]
    lines.extend(["", "## Mixed-Tax Accounts"])
    if mixed_accounts:
        for item in mixed_accounts[:20]:
            codes = ", ".join(sorted(item["tax_codes"].keys()))
            lines.append(f"- `{item['account']}`: {codes}")
    else:
        lines.append("- none detected from account groupings")

    lines.extend(["", "## Implied Rates By Tax Code"])
    for item in profile["rate_profiles"]:
        if not item["implied_rates"]:
            continue
        top_rates = ", ".join(f"{rate} ({count})" for rate, count in list(item["implied_rates"].items())[:5])
        lines.append(f"- `{item['tax_code']}`: {top_rates}")

    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    input_workbook = args.input_workbook or find_default_workbook(base_dir)
    run_dir = create_run_dir(base_dir, input_workbook, run_label=args.run_label, run_dir=args.run_dir)
    output_dir = args.output_dir or (run_dir / "context")
    output_dir.mkdir(parents=True, exist_ok=True)

    wb = load_workbook(input_workbook, data_only=True)
    ws, header_row, inventory = choose_review_sheet(wb)
    headers, rows = extract_transaction_rows(ws, header_row)
    profile = build_profile(input_workbook, ws.title, header_row, headers, rows, inventory, args.include_row_dump)
    summary = build_summary(profile)

    (output_dir / "workbook_profile.json").write_text(json.dumps(profile, indent=2, default=str), encoding="utf-8")
    row_dump_path = output_dir / "workbook_rows.json"
    if args.include_row_dump:
        row_dump_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    elif row_dump_path.exists():
        row_dump_path.unlink()
    (output_dir / "customer_tax_profiles.json").write_text(
        json.dumps(profile["customer_tax_profiles"], indent=2, default=str),
        encoding="utf-8",
    )
    (output_dir / "account_tax_profiles.json").write_text(
        json.dumps(profile["account_tax_profiles"], indent=2, default=str),
        encoding="utf-8",
    )
    (output_dir / "rate_profiles.json").write_text(
        json.dumps(profile["rate_profiles"], indent=2, default=str),
        encoding="utf-8",
    )
    (output_dir / "workbook_summary.md").write_text(summary, encoding="utf-8")
    write_run_manifest(
        run_dir,
        {
            "run_id": run_dir.name,
            "run_label": args.run_label or input_workbook.stem,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source_workbook": str(input_workbook.resolve()),
            "source_workbook_name": input_workbook.name,
            "selected_sheet": ws.title,
            "context_dir": str(output_dir.resolve()),
            "annotations_path": str((run_dir / "annotations.json").resolve()),
            "default_reviewed_workbook": str((run_dir / f"{input_workbook.stem} - Reviewed.xlsx").resolve()),
            "row_dump_generated": args.include_row_dump,
        },
    )
    print(run_dir)


if __name__ == "__main__":
    main()
