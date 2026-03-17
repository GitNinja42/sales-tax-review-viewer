#!/usr/bin/env python3

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any


FEEDBACK_DIR = Path("review-output") / "feedback"
BACKLOG_FILE = "manual-review-backlog.jsonl"
SUMMARY_FILE = "manual-review-summary.json"
_WRITE_LOCK = Lock()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def feedback_dir(base_dir: Path) -> Path:
    return base_dir / FEEDBACK_DIR


def backlog_path(base_dir: Path) -> Path:
    return feedback_dir(base_dir) / BACKLOG_FILE


def summary_path(base_dir: Path) -> Path:
    return feedback_dir(base_dir) / SUMMARY_FILE


def _load_entries(base_dir: Path) -> list[dict[str, Any]]:
    path = backlog_path(base_dir)
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entries.append(json.loads(line))
    return entries


def _build_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    vote_counts = Counter(entry.get("vote") for entry in entries)
    checklist_counts: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"title": None, "entries": 0, "up": 0, "down": 0, "comments": []}
    )

    for entry in entries:
        vote = str(entry.get("vote") or "")
        refs = list(entry.get("checklistRefs") or []) or ["unmapped"]
        titles = list(entry.get("checklistTitles") or []) or ["No checklist mapping"]
        comment = str(entry.get("comment") or "").strip()

        for index, ref in enumerate(refs):
            bucket = checklist_counts[str(ref)]
            bucket["title"] = titles[index] if index < len(titles) else bucket["title"] or str(ref)
            bucket["entries"] += 1
            if vote == "up":
                bucket["up"] += 1
            elif vote == "down":
                bucket["down"] += 1
            if comment:
                bucket["comments"].append(
                    {
                        "submittedAt": entry.get("submittedAt"),
                        "rowNum": entry.get("rowNum"),
                        "vote": vote,
                        "comment": comment,
                    }
                )

    checklist_summary = []
    for ref, bucket in sorted(checklist_counts.items(), key=lambda item: (-item[1]["entries"], item[0])):
        checklist_summary.append(
            {
                "checklistRef": ref,
                "title": bucket["title"] or ref,
                "entries": bucket["entries"],
                "up": bucket["up"],
                "down": bucket["down"],
                "recentComments": bucket["comments"][-5:],
            }
        )

    recent_feedback = [
        {
            "submittedAt": entry.get("submittedAt"),
            "runId": entry.get("runId"),
            "rowNum": entry.get("rowNum"),
            "vote": entry.get("vote"),
            "comment": entry.get("comment"),
            "issueSummary": entry.get("issueSummary"),
            "checklistRefs": entry.get("checklistRefs"),
        }
        for entry in entries[-20:]
    ]

    return {
        "generatedAt": now_iso(),
        "manualReviewRequired": True,
        "note": "Feedback is for human review only. Do not auto-apply manual, prompt, or checklist changes from this file.",
        "totalEntries": len(entries),
        "voteCounts": {"up": vote_counts.get("up", 0), "down": vote_counts.get("down", 0)},
        "byChecklistRef": checklist_summary,
        "recentFeedback": recent_feedback,
    }


def append_feedback(base_dir: Path, entry: dict[str, Any]) -> dict[str, Any]:
    with _WRITE_LOCK:
        target_dir = feedback_dir(base_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        feedback_id = f"fb-{datetime.now().astimezone().strftime('%Y%m%d%H%M%S%f')}"
        payload = {
            "feedbackId": feedback_id,
            "submittedAt": now_iso(),
            "manualReviewRequired": True,
            **entry,
        }

        path = backlog_path(base_dir)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

        entries = _load_entries(base_dir)
        summary_path(base_dir).write_text(json.dumps(_build_summary(entries), indent=2), encoding="utf-8")
        return payload
