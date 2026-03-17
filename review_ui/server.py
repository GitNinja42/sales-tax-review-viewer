#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import subprocess
import sys
from datetime import datetime
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from openpyxl import load_workbook


BASE_DIR = Path(__file__).resolve().parent
PACK_DIR = BASE_DIR.parent
if str(PACK_DIR) not in sys.path:
    sys.path.insert(0, str(PACK_DIR))

from run_utils import create_run_dir, list_run_dirs, load_run_manifest, resolve_run_dir, write_run_manifest  # noqa: E402
from feedback_backlog import append_feedback, backlog_path, summary_path  # noqa: E402
from viewer_payload import build_viewer_payload  # noqa: E402
from workbook_utils import workbook_review_artifacts  # noqa: E402


PREPARE_SCRIPT = PACK_DIR / "prepare_review_context.py"
VALIDATE_SCRIPT = PACK_DIR / "validate_annotations.py"
APPLY_SCRIPT = PACK_DIR / "apply_review_annotations.py"
CLAUDE_REVIEW_SCRIPT = PACK_DIR / "run_claude_review.py"
MAX_BODY_BYTES = 40 * 1024 * 1024
ALLOWED_SUPPORT_EXTENSIONS = {".csv", ".json", ".md", ".pdf", ".txt", ".xlsx", ".xls"}


def safe_name(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "._-" else "-" for char in name.strip())
    return cleaned.strip(".-") or "upload"


def parse_multipart(body: bytes, content_type: str) -> tuple[dict[str, str], dict[str, list[dict[str, object]]]]:
    parser = BytesParser(policy=default)
    message = parser.parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )

    if not message.is_multipart():
        raise ValueError("Expected multipart form data.")

    fields: dict[str, str] = {}
    files: dict[str, list[dict[str, object]]] = {}
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue

        name = part.get_param("name", header="content-disposition")
        if not name:
            continue

        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            files.setdefault(name, []).append(
                {
                    "filename": filename,
                    "content_type": part.get_content_type(),
                    "data": payload,
                }
            )
            continue

        charset = part.get_content_charset() or "utf-8"
        fields[name] = payload.decode(charset, errors="replace")

    return fields, files


def save_upload(destination_dir: Path, upload: dict[str, object], *, force_name: str | None = None) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    original_name = force_name or str(upload["filename"])
    target = destination_dir / safe_name(original_name)
    counter = 1
    while target.exists():
        target = destination_dir / f"{target.stem}-{counter}{target.suffix}"
        counter += 1
    target.write_bytes(bytes(upload["data"]))
    return target


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=PACK_DIR, capture_output=True, text=True)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def concise_process_error(output: str) -> str | None:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return None

    for line in reversed(lines):
        if line.startswith("ERROR:"):
            message = line.partition("ERROR:")[2].strip()
            if message:
                return message

        label, separator, message = line.partition(":")
        if separator and label.split(".")[-1].endswith("Error") and message.strip():
            return message.strip()

    return lines[-1]


def command_failure_details(completed: subprocess.CompletedProcess[str], fallback: str) -> str:
    return (
        concise_process_error(completed.stderr.strip())
        or concise_process_error(completed.stdout.strip())
        or fallback
    )


def count_annotations(run_dir: Path) -> tuple[int, int]:
    annotations_path = run_dir / "annotations.json"
    if not annotations_path.exists():
        return 0, 0
    payload = load_json(annotations_path)
    return len(payload.get("row_annotations", [])), len(payload.get("pattern_annotations", []))


def transaction_rows(run_dir: Path) -> int | None:
    profile_path = run_dir / "context" / "workbook_profile.json"
    if not profile_path.exists():
        return None
    return int(load_json(profile_path).get("row_count") or 0)


def reviewed_workbook_path(manifest: dict[str, object]) -> Path | None:
    path_value = manifest.get("reviewed_workbook") or manifest.get("default_reviewed_workbook")
    if not path_value:
        return None
    path = Path(str(path_value))
    return path if path.exists() else None


def summarize_run(run_dir: Path) -> dict[str, object]:
    manifest = load_run_manifest(run_dir)
    row_annotations, pattern_flags = count_annotations(run_dir)
    reviewed_path = reviewed_workbook_path(manifest)
    has_annotations = (run_dir / "annotations.json").exists()
    support_files = list(manifest.get("support_files") or [])
    row_count = transaction_rows(run_dir)
    review_status = str(manifest.get("review_status") or "")
    review_error = str(manifest.get("review_error") or "").strip() or None
    review_detail = str(manifest.get("review_detail") or "").strip() or None

    if reviewed_path:
        status = "Reviewed"
        next_step = "The reviewed workbook is ready to download."
    elif has_annotations:
        status = "Finalizing"
        next_step = "The review file is ready and the workbook is being finalized."
    elif review_status in {"queued", "running"}:
        status = "Reviewing"
        next_step = review_detail or "Checking workbook rows and building the review file."
    elif review_status == "failed":
        status = "Review failed"
        next_step = review_detail or review_error or "The automatic review stopped before the workbook was finished."
    else:
        status = "Prepared"
        next_step = "Preparing the workbook review."

    payload = {
        "runId": run_dir.name,
        "runLabel": manifest.get("run_label") or run_dir.name,
        "createdAt": manifest.get("created_at"),
        "status": status,
        "nextStep": next_step,
        "workbook": manifest.get("source_workbook_name"),
        "sourceWorkbookPath": manifest.get("source_workbook"),
        "runDir": str(run_dir),
        "notes": manifest.get("operator_notes", ""),
        "supportFiles": support_files,
        "transactionRows": row_count,
        "rowAnnotations": row_annotations,
        "patternFlags": pattern_flags,
        "reviewStatus": review_status or ("reviewed" if reviewed_path else "prepared"),
        "reviewError": review_error,
        "reviewDetail": review_detail,
        "reviewStartedAt": manifest.get("review_started_at"),
        "reviewFinishedAt": manifest.get("review_finished_at"),
        "reviewHeartbeatAt": manifest.get("review_heartbeat_at"),
        "reviewStdoutLog": manifest.get("review_stdout_log"),
        "reviewStderrLog": manifest.get("review_stderr_log"),
        "usageTotalTokens": manifest.get("usage_total_tokens"),
        "usageEstimatedCostUsd": manifest.get("usage_estimated_cost_usd"),
        "hasAnnotations": has_annotations,
        "hasReviewedWorkbook": bool(reviewed_path),
        "downloadUrl": f"/api/runs/{run_dir.name}/download" if reviewed_path else None,
        "viewerUrl": f"/viewer.html?run={run_dir.name}" if has_annotations or reviewed_path else None,
        "outputFileName": reviewed_path.name if reviewed_path else None,
        "outputPath": str(reviewed_path) if reviewed_path else None,
        "engineNotice": "Each run stays isolated in its own folder under review-output/runs.",
    }
    return payload


def recent_runs_payload() -> dict[str, object]:
    runs: list[dict[str, object]] = []
    for path in reversed(list_run_dirs(PACK_DIR)):
        try:
            runs.append(summarize_run(path))
        except FileNotFoundError:
            # A run folder may exist briefly without its manifest if creation failed or was interrupted.
            continue
    return {"runs": runs}


def launch_claude_review(run_dir: Path) -> None:
    claude_bin = os.environ.get("REVIEW_CLAUDE_BIN", "claude")
    heartbeat_seconds = os.environ.get("REVIEW_HEARTBEAT_SECONDS")
    timeout_minutes = os.environ.get("REVIEW_TIMEOUT_MINUTES")
    model = os.environ.get("REVIEW_CLAUDE_MODEL")

    if shutil.which(claude_bin) is None:
        write_run_manifest(
            run_dir,
            {
                "review_status": "failed",
                "review_error": f"Automatic review is not available on PATH: {claude_bin}",
                "review_detail": "The automatic reviewer could not start on this machine.",
                "review_finished_at": now_iso(),
            },
        )
        return

    stdout_log = run_dir / "review_runner.stdout.log"
    stderr_log = run_dir / "review_runner.stderr.log"
    write_run_manifest(
        run_dir,
        {
            "review_status": "queued",
            "review_error": None,
            "review_started_at": now_iso(),
            "review_finished_at": None,
            "review_detail": "Preparing the workbook review.",
            "review_stdout_log": str(stdout_log.resolve()),
            "review_stderr_log": str(stderr_log.resolve()),
        },
    )

    stdout_handle = stdout_log.open("ab")
    stderr_handle = stderr_log.open("ab")
    try:
        command = [sys.executable, str(CLAUDE_REVIEW_SCRIPT), "--run-dir", str(run_dir), "--claude-bin", claude_bin]
        if heartbeat_seconds:
            command.extend(["--heartbeat-seconds", heartbeat_seconds])
        if timeout_minutes:
            command.extend(["--timeout-minutes", timeout_minutes])
        if model:
            command.extend(["--model", model])

        process = subprocess.Popen(command, cwd=PACK_DIR, stdout=stdout_handle, stderr=stderr_handle, start_new_session=True)
    except Exception as exc:  # noqa: BLE001
        write_run_manifest(
            run_dir,
            {
                "review_status": "failed",
                "review_error": f"Could not launch Claude review runner: {exc}",
                "review_detail": "The automatic review could not be started.",
                "review_finished_at": now_iso(),
            },
        )
    else:
        write_run_manifest(
            run_dir,
            {
                "review_status": "running",
                "review_pid": process.pid,
                "review_started_at": now_iso(),
                "review_detail": "Checking workbook rows and drafting annotations.",
            },
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()


class ReviewUIHandler(BaseHTTPRequestHandler):
    server_version = "ReviewUI/0.4"

    def do_GET(self) -> None:
        self._dispatch_request(head_only=False)

    def do_HEAD(self) -> None:
        self._dispatch_request(head_only=True)

    def _dispatch_request(self, *, head_only: bool) -> None:
        route = urlparse(self.path).path

        if route in {"/", "/index.html"}:
            self._serve_static("index.html", "text/html; charset=utf-8", head_only=head_only)
            return
        if route == "/viewer.html":
            self._serve_static("viewer.html", "text/html; charset=utf-8", head_only=head_only)
            return
        if route == "/styles.css":
            self._serve_static("styles.css", "text/css; charset=utf-8", head_only=head_only)
            return
        if route == "/app.js":
            self._serve_static("app.js", "application/javascript; charset=utf-8", head_only=head_only)
            return
        if route == "/viewer.js":
            self._serve_static("viewer.js", "application/javascript; charset=utf-8", head_only=head_only)
            return
        if route == "/favicon.svg":
            self._serve_static("favicon.svg", "image/svg+xml", head_only=head_only)
            return
        if route == "/api/runs":
            self._send_json(HTTPStatus.OK, recent_runs_payload())
            return
        if route.startswith("/api/runs/") and route.endswith("/viewer"):
            self._serve_run_viewer(route)
            return
        if route.startswith("/api/runs/") and route.endswith("/download"):
            self._serve_download(route, head_only=head_only)
            return
        if route.startswith("/api/runs/"):
            self._serve_run(route)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/review":
            self._handle_prepare_run()
            return
        if route.startswith("/api/runs/") and route.endswith("/apply"):
            self._handle_apply_annotations(route)
            return
        if route.startswith("/api/runs/") and route.endswith("/dismiss"):
            self._handle_dismiss_reason(route)
            return
        if route.startswith("/api/runs/") and route.endswith("/regenerate"):
            self._handle_regenerate_workbook(route)
            return
        if route.startswith("/api/runs/") and route.endswith("/flag"):
            self._handle_manual_flag(route)
            return
        if route.startswith("/api/runs/") and route.endswith("/annotate"):
            self._handle_edit_annotation(route)
            return
        if route.startswith("/api/runs/") and route.endswith("/feedback"):
            self._handle_feedback_submission(route)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def _handle_prepare_run(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "No request body received."})
            return
        if content_length > MAX_BODY_BYTES:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": f"Upload is too large. Keep the review pack below {MAX_BODY_BYTES // (1024 * 1024)} MB."},
            )
            return

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Expected multipart form data."})
            return

        body = self.rfile.read(content_length)
        try:
            fields, files = parse_multipart(body, content_type)
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        workbook_uploads = files.get("workbook", [])
        if len(workbook_uploads) != 1:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Upload exactly one workbook to continue."})
            return

        workbook_upload = workbook_uploads[0]
        workbook_name = str(workbook_upload["filename"])
        if Path(workbook_name).suffix.lower() != ".xlsx":
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "The source workbook must be an .xlsx file."})
            return

        run_label = fields.get("run_label", "").strip() or None
        run_dir = create_run_dir(PACK_DIR, Path(workbook_name), run_label=run_label)
        input_dir = run_dir / "inputs"
        support_dir = input_dir / "support"
        workbook_path = save_upload(input_dir, workbook_upload)

        try:
            uploaded_workbook = load_workbook(workbook_path, read_only=True, data_only=True)
            review_artifacts = workbook_review_artifacts(uploaded_workbook)
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(run_dir, ignore_errors=True)
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "The uploaded workbook could not be opened.",
                    "details": str(exc),
                },
            )
            return
        finally:
            try:
                uploaded_workbook.close()
            except Exception:  # noqa: BLE001
                pass

        if review_artifacts:
            shutil.rmtree(run_dir, ignore_errors=True)
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "This workbook already looks reviewed. Upload the original source workbook instead.",
                    "details": "; ".join(review_artifacts),
                },
            )
            return

        saved_support_files: list[Path] = []
        for upload in files.get("support_files", []):
            extension = Path(str(upload["filename"])).suffix.lower()
            if extension and extension not in ALLOWED_SUPPORT_EXTENSIONS:
                continue
            saved_support_files.append(save_upload(support_dir, upload))

        command = [
            sys.executable,
            str(PREPARE_SCRIPT),
            "--input-workbook",
            str(workbook_path),
            "--run-dir",
            str(run_dir),
        ]
        if run_label:
            command.extend(["--run-label", run_label])
        completed = run_command(command)
        if completed.returncode != 0:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "The review run could not be prepared.",
                    "details": command_failure_details(completed, "No additional details were returned."),
                },
            )
            return

        write_run_manifest(
            run_dir,
            {
                "operator_notes": fields.get("notes", "").strip(),
                "support_files": [path.name for path in saved_support_files],
                "input_dir": str(input_dir.resolve()),
            },
        )
        launch_claude_review(run_dir)
        self._send_json(HTTPStatus.OK, summarize_run(run_dir))

    def _handle_apply_annotations(self, route: str) -> None:
        parts = route.strip("/").split("/")
        if len(parts) != 4:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        run_id = parts[2]
        try:
            run_dir = resolve_run_dir(PACK_DIR, PACK_DIR / "review-output" / "runs" / run_id)
        except FileNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > MAX_BODY_BYTES:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": f"Upload is too large. Keep the review pack below {MAX_BODY_BYTES // (1024 * 1024)} MB."},
            )
            return

        if content_length > 0:
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Expected multipart form data."})
                return
            body = self.rfile.read(content_length)
            try:
                _, files = parse_multipart(body, content_type)
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            annotation_uploads = files.get("annotations", [])
            if len(annotation_uploads) > 1:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Upload at most one annotations.json file."})
                return
            if annotation_uploads:
                annotation_upload = annotation_uploads[0]
                if Path(str(annotation_upload["filename"])).suffix.lower() != ".json":
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Annotations file must be a .json file."})
                    return
                target = run_dir / "annotations.json"
                target.write_bytes(bytes(annotation_upload["data"]))

        annotations_path = run_dir / "annotations.json"
        if not annotations_path.exists():
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "This run does not have annotations.json yet. Upload it here after the agent review step."},
            )
            return

        validate_completed = run_command([sys.executable, str(VALIDATE_SCRIPT), "--run-dir", str(run_dir)])
        if validate_completed.returncode != 0:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "Annotations did not validate for this run.",
                    "details": command_failure_details(validate_completed, "Validation failed."),
                },
            )
            return

        apply_completed = run_command([sys.executable, str(APPLY_SCRIPT), "--run-dir", str(run_dir)])
        if apply_completed.returncode != 0:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "The reviewed workbook could not be written for this run.",
                    "details": command_failure_details(apply_completed, "Workbook write failed."),
                },
            )
            return

        self._send_json(HTTPStatus.OK, summarize_run(run_dir))

    def _handle_dismiss_reason(self, route: str) -> None:
        parts = route.strip("/").split("/")
        if len(parts) != 4:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        run_id = parts[2]
        try:
            run_dir = resolve_run_dir(PACK_DIR, PACK_DIR / "review-output" / "runs" / run_id)
        except FileNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > 64 * 1024:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid request body."})
            return

        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Expected JSON."})
            return

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON."})
            return

        row_num = payload.get("rowNum")
        dismissed = bool(payload.get("dismissed", False))

        if not row_num:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "rowNum is required."})
            return

        annotations_path = run_dir / "annotations.json"
        if not annotations_path.exists():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "No annotations found for this run."})
            return

        try:
            annotations = json.loads(annotations_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Could not read annotations."})
            return

        updated = False
        for item in annotations.get("row_annotations", []):
            if int(item.get("source_row", -1)) != int(row_num):
                continue
            item["_dismissed"] = dismissed
            updated = True
            break

        if not updated:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Row annotation not found."})
            return

        annotations_path.write_text(json.dumps(annotations, indent=2, ensure_ascii=False), encoding="utf-8")
        self._send_json(HTTPStatus.OK, {"message": "Dismiss state saved.", "rowNum": row_num, "dismissed": dismissed})

    def _handle_manual_flag(self, route: str) -> None:
        parts = route.strip("/").split("/")
        if len(parts) != 4:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        run_id = parts[2]
        try:
            run_dir = resolve_run_dir(PACK_DIR, PACK_DIR / "review-output" / "runs" / run_id)
        except FileNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        annotations_path = run_dir / "annotations.json"
        if not annotations_path.exists():
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "No annotations found for this run."})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8")) if content_length else {}
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON."})
            return

        row_num = payload.get("rowNum")
        if not row_num:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "rowNum is required."})
            return

        annotations = json.loads(annotations_path.read_text(encoding="utf-8"))

        # Check if row already has an annotation.
        for item in annotations.get("row_annotations", []):
            if int(item.get("source_row", -1)) == int(row_num):
                self._send_json(HTTPStatus.CONFLICT, {"error": "Row already has an annotation."})
                return

        new_annotation = {
            "source_row": int(row_num),
            "status": "Review Needed",
            "issue_summary": "Manually flagged for review.",
            "checklist_refs": [],
            "highlight_columns": [],
        }
        annotations.setdefault("row_annotations", []).append(new_annotation)
        annotations_path.write_text(json.dumps(annotations, indent=2, ensure_ascii=False), encoding="utf-8")

        # Build the viewer-format annotation to return to the client.
        viewer_annotation = {
            "status": "Review Needed",
            "issueSummary": "Manually flagged for review.",
            "checklistRefs": [],
            "checklistTitles": [],
            "missingContext": [],
            "suggestedNextStep": None,
            "highlightColumns": [],
            "_dismissed": False,
        }
        self._send_json(HTTPStatus.OK, {"message": "Row flagged.", "rowNum": row_num, "annotation": viewer_annotation})

    def _handle_regenerate_workbook(self, route: str) -> None:
        parts = route.strip("/").split("/")
        if len(parts) != 4:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        run_id = parts[2]
        try:
            run_dir = resolve_run_dir(PACK_DIR, PACK_DIR / "review-output" / "runs" / run_id)
        except FileNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        annotations_path = run_dir / "annotations.json"
        if not annotations_path.exists():
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "No annotations found for this run."})
            return

        try:
            result = subprocess.run(
                [sys.executable, str(PACK_DIR / "apply_review_annotations.py"), "--run-dir", str(run_dir)],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output_path = result.stdout.strip()
            self._send_json(HTTPStatus.OK, {
                "message": "Workbook regenerated.",
                "outputPath": output_path,
            })
        except subprocess.CalledProcessError as exc:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                "error": f"Workbook generation failed: {exc.stderr or str(exc)}",
            })
        except subprocess.TimeoutExpired:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                "error": "Workbook generation timed out.",
            })

    def _handle_edit_annotation(self, route: str) -> None:
        """Update editable fields on a row annotation (issue_summary, suggested_next_step)."""
        parts = route.strip("/").split("/")
        if len(parts) != 4:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        run_id = parts[2]
        try:
            run_dir = resolve_run_dir(PACK_DIR, PACK_DIR / "review-output" / "runs" / run_id)
        except FileNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid request body."})
            return

        try:
            payload = json.loads(self.rfile.read(content_length))
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON."})
            return

        row_num = payload.get("rowNum")
        if not row_num:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "rowNum is required."})
            return

        editable_fields = {"issue_summary", "suggested_next_step", "status"}
        updates = {k: v for k, v in payload.items() if k in editable_fields}
        if not updates:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "No editable fields provided."})
            return

        annotations_path = run_dir / "annotations.json"
        if not annotations_path.exists():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "No annotations found."})
            return

        annotations = json.loads(annotations_path.read_text(encoding="utf-8"))
        updated = False
        for item in annotations.get("row_annotations", []):
            if int(item.get("source_row", -1)) != int(row_num):
                continue
            for field, value in updates.items():
                item[field] = value
            updated = True
            break

        if not updated:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Row annotation not found."})
            return

        annotations_path.write_text(json.dumps(annotations, indent=2, ensure_ascii=False), encoding="utf-8")
        self._send_json(HTTPStatus.OK, {"message": "Annotation updated.", "rowNum": row_num, "updates": updates})

    def _handle_feedback_submission(self, route: str) -> None:
        parts = route.strip("/").split("/")
        if len(parts) != 4:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        run_id = parts[2]
        try:
            run_dir = resolve_run_dir(PACK_DIR, PACK_DIR / "review-output" / "runs" / run_id)
        except FileNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "No feedback payload received."})
            return
        if content_length > 256 * 1024:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Feedback payload is too large."})
            return

        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Feedback must be submitted as JSON."})
            return

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Feedback payload could not be read."})
            return

        try:
            row_num = int(payload.get("rowNum"))
        except (TypeError, ValueError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Select a valid row before submitting feedback."})
            return

        vote = str(payload.get("vote") or "").strip().lower()
        if vote not in {"up", "down"}:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Choose thumbs up or thumbs down before saving feedback."})
            return

        comment = str(payload.get("comment") or "").strip()
        if len(comment) > 4000:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Keep feedback comments under 4,000 characters."})
            return

        try:
            viewer_payload = build_viewer_payload(PACK_DIR, run_dir, summarize_run(run_dir))
        except FileNotFoundError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        row_payload = next((item for item in viewer_payload["rows"] if int(item["rowNum"]) == row_num), None)
        if row_payload is None:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "That row is not available for this run."})
            return

        annotation = dict(row_payload.get("annotation") or {})
        saved_feedback = append_feedback(
            PACK_DIR,
            {
                "source": "viewer-row-feedback",
                "reviewTarget": "manual-guidance-review",
                "runId": run_id,
                "runLabel": viewer_payload["run"].get("runLabel"),
                "workbook": viewer_payload["run"].get("viewerWorkbook"),
                "rowNum": row_num,
                "vote": vote,
                "comment": comment,
                "status": annotation.get("status"),
                "issueSummary": annotation.get("issueSummary"),
                "checklistRefs": list(annotation.get("checklistRefs") or []),
                "checklistTitles": list(annotation.get("checklistTitles") or []),
                "suggestedNextStep": annotation.get("suggestedNextStep"),
                "name": row_payload.get("name"),
                "account": row_payload.get("account"),
                "taxCode": row_payload.get("taxCode"),
                "memoDescription": row_payload.get("memoDescription"),
            },
        )

        self._send_json(
            HTTPStatus.OK,
            {
                "message": "Saved to the manual-review backlog. Guidance does not change automatically.",
                "feedback": saved_feedback,
                "backlogPath": str(backlog_path(PACK_DIR)),
                "summaryPath": str(summary_path(PACK_DIR)),
            },
        )

    def _serve_run(self, route: str) -> None:
        parts = route.strip("/").split("/")
        if len(parts) != 3:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return
        run_id = parts[2]
        try:
            run_dir = resolve_run_dir(PACK_DIR, PACK_DIR / "review-output" / "runs" / run_id)
        except FileNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return
        try:
            payload = summarize_run(run_dir)
        except FileNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return
        self._send_json(HTTPStatus.OK, payload)

    def _serve_run_viewer(self, route: str) -> None:
        parts = route.strip("/").split("/")
        if len(parts) != 4:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        run_id = parts[2]
        try:
            run_dir = resolve_run_dir(PACK_DIR, PACK_DIR / "review-output" / "runs" / run_id)
        except FileNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        try:
            payload = build_viewer_payload(PACK_DIR, run_dir, summarize_run(run_dir))
        except FileNotFoundError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        self._send_json(HTTPStatus.OK, payload)

    def _serve_static(self, file_name: str, content_type: str, *, head_only: bool) -> None:
        path = BASE_DIR / file_name
        if not path.exists():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Static asset not found."})
            return

        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _serve_download(self, route: str, *, head_only: bool) -> None:
        parts = route.strip("/").split("/")
        if len(parts) != 4:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        run_id = parts[2]
        try:
            run_dir = resolve_run_dir(PACK_DIR, PACK_DIR / "review-output" / "runs" / run_id)
        except FileNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Review run not found."})
            return

        reviewed_path = reviewed_workbook_path(load_run_manifest(run_dir))
        if reviewed_path is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Reviewed workbook is not available for this run."})
            return

        body = reviewed_path.read_bytes()
        content_type = mimetypes.guess_type(reviewed_path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{reviewed_path.name}"')
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local browser UI for the sales-tax review pack.")
    parser.add_argument("--host", default="127.0.0.1", help="Hostname to bind the server to.")
    parser.add_argument("--port", default=8790, type=int, help="Port to bind the server to.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    (PACK_DIR / "review-output" / "runs").mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), ReviewUIHandler)
    print(f"Review UI running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
