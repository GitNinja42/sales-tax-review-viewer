#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


def slugify_for_path(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return slug or "review-run"


def runs_root(base_dir: Path) -> Path:
    return base_dir / "review-output" / "runs"


def manifest_path(run_dir: Path) -> Path:
    return run_dir / "run_manifest.json"


def normalize_run_dir(base_dir: Path, run_dir: Path) -> Path:
    path = run_dir.expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def build_run_id(workbook_path: Path, run_label: str | None = None) -> str:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    label = run_label or workbook_path.stem
    return f"{timestamp}--{slugify_for_path(label)}"


def create_run_dir(base_dir: Path, workbook_path: Path, run_label: str | None = None, run_dir: Path | None = None) -> Path:
    if run_dir is not None:
        # Explicit run directory: use as-is (may already exist).
        resolved = normalize_run_dir(base_dir, run_dir)
    else:
        # Auto-generated: avoid collisions if the directory already exists.
        resolved = runs_root(base_dir) / build_run_id(workbook_path, run_label)
        if resolved.exists():
            base_name = resolved.name
            for suffix in range(2, 100):
                candidate = resolved.parent / f"{base_name}-{suffix}"
                if not candidate.exists():
                    resolved = candidate
                    break
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def list_run_dirs(base_dir: Path) -> list[Path]:
    root = runs_root(base_dir)
    if not root.exists():
        return []
    return sorted((path for path in root.iterdir() if path.is_dir()), key=lambda item: item.name)


def resolve_run_dir(base_dir: Path, run_dir: Path | None = None) -> Path:
    if run_dir is not None:
        resolved = normalize_run_dir(base_dir, run_dir)
        if not resolved.exists():
            raise FileNotFoundError(f"Run directory not found: {resolved}")
        return resolved

    run_dirs = list_run_dirs(base_dir)
    if not run_dirs:
        raise FileNotFoundError("No review runs found under review-output/runs. Run prepare_review_context.py first or pass --run-dir.")
    if len(run_dirs) == 1:
        return run_dirs[0]

    names = ", ".join(path.name for path in run_dirs[-5:])
    raise FileExistsError(
        "Multiple review runs found under review-output/runs. Pass --run-dir to avoid cross-contaminating runs. "
        f"Recent runs: {names}"
    )


def load_run_manifest(run_dir: Path) -> dict[str, object]:
    path = manifest_path(run_dir)
    if not path.exists():
        raise FileNotFoundError(f"Run manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_run_manifest(run_dir: Path, updates: dict[str, object]) -> Path:
    path = manifest_path(run_dir)
    payload: dict[str, object] = {}
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(updates)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path
