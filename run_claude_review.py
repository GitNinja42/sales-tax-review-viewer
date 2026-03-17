#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import select
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

from claude_usage import write_run_usage_summary
from run_utils import load_run_manifest, normalize_run_dir, write_run_manifest


PREPARE_SCRIPT = "prepare_review_context.py"
VALIDATE_SCRIPT = "validate_annotations.py"
APPLY_SCRIPT = "apply_review_annotations.py"
ROW_REVIEW_PROMPT = "row_review_agent_prompt.txt"
PATTERN_REVIEW_PROMPT = "pattern_review_agent_prompt.txt"
RECONCILE_REVIEW_PROMPT = "reconcile_review_agent_prompt.txt"
ANNOTATION_SCHEMA = "review_annotation_schema.json"
CONTROL_LIBRARY = "sales-tax-control-library.json"


@dataclass(frozen=True)
class ReviewAgentSpec:
    key: str
    label: str
    prompt_file: str
    artifact_name: str
    final_output: bool = False


@dataclass
class RunningAgent:
    spec: ReviewAgentSpec
    runtime_dir: Path
    artifact_path: Path
    response_path: Path
    stderr_path: Path
    process: subprocess.Popen[str]
    stdout_handle: TextIO | None
    stderr_handle: TextIO
    latest_progress: str
    last_result_json: dict | None = None


ROW_REVIEW = ReviewAgentSpec(
    key="row_review",
    label="Row Reviewer",
    prompt_file=ROW_REVIEW_PROMPT,
    artifact_name="row_review_annotations.json",
)
PATTERN_REVIEW = ReviewAgentSpec(
    key="pattern_review",
    label="Pattern Reviewer",
    prompt_file=PATTERN_REVIEW_PROMPT,
    artifact_name="pattern_review_annotations.json",
)
RECONCILE_REVIEW = ReviewAgentSpec(
    key="reconcile_review",
    label="Reconciler",
    prompt_file=RECONCILE_REVIEW_PROMPT,
    artifact_name="annotations.json",
    final_output=True,
)
ALL_REVIEW_AGENTS = (ROW_REVIEW, PATTERN_REVIEW, RECONCILE_REVIEW)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare or reuse a review run, invoke Claude CLI reviewers, then validate and apply the workbook annotations.",
    )
    parser.add_argument("--input-workbook", type=Path, default=None)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--run-label", type=str, default=None)
    parser.add_argument("--include-row-dump", action="store_true")
    parser.add_argument(
        "--support-file",
        action="append",
        default=[],
        help="Optional support file to copy into <run-dir>/inputs/support before Claude reviews the workbook.",
    )
    parser.add_argument("--claude-bin", type=str, default="claude")
    parser.add_argument("--model", type=str, default="claude-opus-4-6")
    parser.add_argument(
        "--allowed-tools",
        type=str,
        default="Read,Write,Edit,Bash(python3 *),Glob,Grep",
        help="Comma-separated list of tools to allow in Claude CLI.",
    )
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=20,
        help="Fail the run if Claude has not exited after this many minutes.",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=int,
        default=10,
        help="How often the runner should check for streaming progress.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=100,
        help="Maximum agentic turns per Claude invocation.",
    )
    parser.add_argument(
        "--max-budget-usd",
        type=float,
        default=None,
        help="Cost ceiling per Claude invocation (USD).",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def update_review_manifest(run_dir: Path, **updates: object) -> None:
    updates.setdefault("review_heartbeat_at", now_iso())
    write_run_manifest(run_dir, updates)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def run_subprocess(
    command: list[str],
    *,
    cwd: Path,
    input_text: str | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=capture_output,
        check=False,
    )


def prepare_or_reuse_run(base_dir: Path, args: argparse.Namespace) -> Path:
    if args.run_dir is not None:
        resolved = normalize_run_dir(base_dir, args.run_dir)
        if (resolved / "run_manifest.json").exists():
            return resolved

    command = [sys.executable, str(base_dir / PREPARE_SCRIPT)]
    if args.input_workbook is not None:
        command.extend(["--input-workbook", str(args.input_workbook)])
    if args.run_dir is not None:
        command.extend(["--run-dir", str(args.run_dir)])
    if args.run_label:
        command.extend(["--run-label", args.run_label])
    if args.include_row_dump:
        command.append("--include-row-dump")

    completed = run_subprocess(command, cwd=base_dir, capture_output=True)
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip() or "prepare_review_context.py failed."
        raise RuntimeError(details)

    output = completed.stdout.strip().splitlines()
    if not output:
        raise RuntimeError("prepare_review_context.py did not print a run directory.")
    return Path(output[-1]).resolve()


def agent_runtime_dir(run_dir: Path, spec: ReviewAgentSpec) -> Path:
    return run_dir / "agent_runs" / spec.key


def agent_artifact_path(run_dir: Path, spec: ReviewAgentSpec) -> Path:
    return run_dir / spec.artifact_name


def build_agent_manifest(run_dir: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for spec in ALL_REVIEW_AGENTS:
        runtime_dir = agent_runtime_dir(run_dir, spec)
        entries.append(
            {
                "name": spec.key,
                "label": spec.label,
                "status": "pending",
                "artifact_path": str(agent_artifact_path(run_dir, spec).resolve()),
                "runtime_dir": str(runtime_dir.resolve()),
                "response_path": str((runtime_dir / "claude_response.json").resolve()),
                "stderr_path": str((runtime_dir / "stderr.log").resolve()),
            }
        )
    return entries


def set_agent_status(
    agent_entries: list[dict[str, object]],
    spec: ReviewAgentSpec,
    *,
    status: str,
    timestamp_field: str | None = None,
) -> None:
    for entry in agent_entries:
        if entry.get("name") == spec.key:
            entry["status"] = status
            if timestamp_field:
                entry[timestamp_field] = now_iso()
            return


def clear_generated_artifacts(run_dir: Path, manifest: dict[str, object]) -> None:
    targets = [
        run_dir / "annotations.json",
        run_dir / "row_review_annotations.json",
        run_dir / "pattern_review_annotations.json",
        run_dir / "usage_summary.json",
    ]
    reviewed_path = manifest.get("default_reviewed_workbook")
    if reviewed_path:
        targets.append(Path(str(reviewed_path)))
    explicit_reviewed_path = manifest.get("reviewed_workbook")
    if explicit_reviewed_path:
        targets.append(Path(str(explicit_reviewed_path)))

    for path in targets:
        if path.exists():
            path.unlink()

    agent_runs_dir = run_dir / "agent_runs"
    if agent_runs_dir.exists():
        shutil.rmtree(agent_runs_dir)


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def stage_support_files(run_dir: Path, support_files: list[str]) -> list[str]:
    if not support_files:
        return []

    support_dir = run_dir / "inputs" / "support"
    support_dir.mkdir(parents=True, exist_ok=True)
    saved_names: list[str] = []

    for raw_path in support_files:
        source = Path(raw_path).expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"Support file not found: {source}")

        target = support_dir / source.name
        counter = 1
        while target.exists() and source != target:
            target = support_dir / f"{source.stem}-{counter}{source.suffix}"
            counter += 1
        shutil.copy2(source, target)
        saved_names.append(target.name)

    return saved_names


def get_skippable_controls(base_dir: Path) -> list[str]:
    """Return control IDs that require support docs (requires_support_docs: true)."""
    library_path = base_dir / CONTROL_LIBRARY
    if not library_path.exists():
        return []
    try:
        library = json.loads(library_path.read_text(encoding="utf-8"))
        return [
            c["control_id"]
            for c in library.get("controls", [])
            if c.get("requires_support_docs")
        ]
    except (json.JSONDecodeError, KeyError):
        return []


def build_runtime_context(
    base_dir: Path,
    run_dir: Path,
    manifest: dict[str, object],
    spec: ReviewAgentSpec,
) -> str:
    """Build the --append-system-prompt string with runtime paths and stage rules."""
    artifact_path = agent_artifact_path(run_dir, spec)
    runtime_dir = agent_runtime_dir(run_dir, spec)
    schema_path = base_dir / ANNOTATION_SCHEMA
    context_dir = Path(str(manifest["context_dir"]))
    support_dir = run_dir / "inputs" / "support"
    support_files = sorted(path for path in support_dir.iterdir() if path.is_file()) if support_dir.exists() else []
    support_lines = "\n".join(f"- `{path}`" for path in support_files) if support_files else "- none"

    # When no support docs are uploaded, tell the agent to skip controls that require them.
    skip_controls_note = ""
    if not support_files:
        skippable = get_skippable_controls(base_dir)
        if skippable:
            ids = ", ".join(skippable)
            skip_controls_note = (
                f"No support documents were provided for this run. "
                f"Skip the following controls entirely (they cannot be assessed without supplementary documents): {ids}. "
                f"Do not flag rows under these controls or mention them in your review.\n\n"
            )

    candidate_artifacts = ""
    if spec is RECONCILE_REVIEW:
        candidate_artifacts = (
            "Candidate reviewer artifacts:\n"
            f"- row-review candidate artifact: `{agent_artifact_path(run_dir, ROW_REVIEW)}`\n"
            f"- pattern-review candidate artifact: `{agent_artifact_path(run_dir, PATTERN_REVIEW)}`\n\n"
        )

    stage_rules = []
    if spec.final_output:
        stage_rules.extend(
            [
                f"- read `{agent_artifact_path(run_dir, ROW_REVIEW)}` and `{agent_artifact_path(run_dir, PATTERN_REVIEW)}` before finalizing your output",
                "- treat overlap between candidate reviewers as a strong signal, but not as an automatic yes",
                "- inspect rows mentioned in any candidate row annotation or pattern row_refs before deciding what survives into the final file",
                "- group recurring checklist-backed issues into helpful pattern annotations when they explain clusters of flagged rows",
            ]
        )
    else:
        stage_rules.extend(
            [
                "- do not inspect sibling reviewer outputs or wait for them",
                "- your artifact is a candidate review artifact, not the final workbook review",
            ]
        )

    return (
        "Runtime details for this prepared run:\n"
        f"- repository root: `{base_dir}`\n"
        f"- run directory: `{run_dir}`\n"
        f"- source workbook: `{manifest['source_workbook']}`\n"
        f"- context directory: `{context_dir}`\n"
        f"- artifact target: `{artifact_path}`\n"
        f"- annotation schema: `{schema_path}`\n"
        f"- support files directory: `{support_dir}`\n"
        f"- stage scratch directory: `{runtime_dir}`\n\n"
        f"{candidate_artifacts}"
        f"{skip_controls_note}"
        "Support files actually present for this run:\n"
        f"{support_lines}\n\n"
        "Execution-specific rules:\n"
        "- prefer an actual client checklist/support file from this run over the baked-in control library when relevant\n"
        "- do not inspect prior run outputs, prior annotations.json files, or reviewed workbooks from other runs\n"
        "- review the workbook line by line and in totality\n"
        f"- write exactly one artifact to `{artifact_path}`\n"
        f"- make sure the JSON matches `{schema_path}`\n"
        f"- keep any temporary scratch work inside `{runtime_dir}` only\n"
        "- do not edit the workbook directly; the wrapper will validate and apply the final annotations after the reconcile stage\n"
        f"- before finishing, re-open `{artifact_path}` and confirm it is valid JSON with the required top-level keys\n"
        + "\n".join(stage_rules)
        + "\n"
    )


def build_claude_command(
    args: argparse.Namespace,
    task_prompt: str,
    runtime_context: str,
) -> list[str]:
    command = [
        args.claude_bin,
        "-p",
        task_prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--append-system-prompt",
        runtime_context,
        "--allowedTools",
        args.allowed_tools,
        "--dangerously-skip-permissions",
        "--max-turns",
        str(args.max_turns),
    ]
    if args.model:
        command.extend(["--model", args.model])
    if args.max_budget_usd is not None:
        command.extend(["--max-budget-usd", str(args.max_budget_usd)])
    return command


def format_elapsed(seconds: float) -> str:
    rounded = int(seconds)
    minutes, secs = divmod(rounded, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def parse_stream_progress(line: str) -> str | None:
    """Extract a human-readable progress string from a stream-json event line."""
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None

    event_type = event.get("type")

    # Assistant events contain tool_use and text in message.content[]
    if event_type == "assistant":
        message = event.get("message") or {}
        content_list = message.get("content") or []
        if not isinstance(content_list, list):
            return None

        for block in content_list:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")

            if block_type == "tool_use":
                tool_name = block.get("name") or ""
                tool_input = block.get("input") or {}

                if tool_name == "Read":
                    file_path = tool_input.get("file_path", "")
                    if file_path:
                        name = Path(file_path).name
                        return f"Reading {name}"
                if tool_name == "Write":
                    file_path = tool_input.get("file_path", "")
                    if file_path:
                        name = Path(file_path).name
                        return f"Writing {name}"
                if tool_name == "Bash":
                    cmd = str(tool_input.get("command", ""))
                    if "validate_annotations" in cmd:
                        return "Validating annotations"
                    if cmd:
                        short = cmd[:60].rstrip()
                        return f"Running: {short}"
                if tool_name == "Glob":
                    return "Searching files"
                if tool_name == "Grep":
                    pattern = tool_input.get("pattern", "")
                    return f"Searching for: {pattern[:40]}" if pattern else "Searching content"

            if block_type == "text":
                text = block.get("text", "")
                if isinstance(text, str) and text.strip():
                    cleaned = " ".join(text.strip().split())
                    if len(cleaned) > 120:
                        cleaned = f"{cleaned[:117].rstrip()}..."
                    return cleaned

    return None


def drain_stream_progress(agent: RunningAgent) -> None:
    """Read available stream-json lines without blocking, update agent progress."""
    if agent.stdout_handle is None or agent.stdout_handle.closed:
        return

    while True:
        ready, _, _ = select.select([agent.stdout_handle], [], [], 0)
        if not ready:
            break
        line = agent.stdout_handle.readline()
        if not line:
            break
        stripped = line.strip()
        if not stripped:
            continue

        # Capture every JSON event so we can save the final result later
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                agent.last_result_json = parsed
        except json.JSONDecodeError:
            pass

        progress = parse_stream_progress(stripped)
        if progress:
            agent.latest_progress = progress


def save_stream_result(agent: RunningAgent) -> None:
    """After the process exits, read any remaining stdout and save the last JSON result."""
    last_json = agent.last_result_json

    # Also drain any remaining lines not yet consumed
    if agent.stdout_handle is not None and not agent.stdout_handle.closed:
        for line in agent.stdout_handle:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    last_json = parsed
            except json.JSONDecodeError:
                continue

    if last_json is not None:
        agent.response_path.write_text(json.dumps(last_json, indent=2), encoding="utf-8")


def spawn_agent(
    *,
    base_dir: Path,
    manifest: dict[str, object],
    args: argparse.Namespace,
    run_dir: Path,
    spec: ReviewAgentSpec,
) -> RunningAgent:
    runtime_dir = agent_runtime_dir(run_dir, spec)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = agent_artifact_path(run_dir, spec)
    response_path = runtime_dir / "claude_response.json"
    stderr_path = runtime_dir / "stderr.log"

    task_prompt = read_text(base_dir / spec.prompt_file)
    runtime_context = build_runtime_context(base_dir, run_dir, manifest, spec)
    command = build_claude_command(args, task_prompt, runtime_context)

    stderr_handle = stderr_path.open("w", encoding="utf-8")

    # Strip CLAUDECODE env var so spawned Claude processes don't refuse to start
    # (Claude Code detects nested sessions via this variable).
    spawn_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    # Ensure agents have enough output token headroom for large annotation artifacts.
    spawn_env.setdefault("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "128000")

    process = subprocess.Popen(
        command,
        cwd=base_dir,
        stdout=subprocess.PIPE,
        stderr=stderr_handle,
        text=True,
        env=spawn_env,
    )

    return RunningAgent(
        spec=spec,
        runtime_dir=runtime_dir,
        artifact_path=artifact_path,
        response_path=response_path,
        stderr_path=stderr_path,
        process=process,
        stdout_handle=process.stdout,
        stderr_handle=stderr_handle,
        latest_progress="Starting review.",
    )


def close_agent(agent: RunningAgent) -> None:
    if agent.stdout_handle and not agent.stdout_handle.closed:
        agent.stdout_handle.close()
    agent.stderr_handle.close()


def terminate_agents(agents: list[RunningAgent]) -> None:
    for agent in agents:
        if agent.process.poll() is None:
            agent.process.terminate()
    for agent in agents:
        if agent.process.poll() is None:
            try:
                agent.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                agent.process.kill()
                agent.process.wait()
        close_agent(agent)


def validate_annotation_artifact(base_dir: Path, run_dir: Path, artifact_path: Path, label: str) -> None:
    validate = run_subprocess(
        [
            sys.executable,
            str(base_dir / VALIDATE_SCRIPT),
            "--run-dir",
            str(run_dir),
            "--annotations",
            str(artifact_path),
        ],
        cwd=base_dir,
        capture_output=True,
    )
    if validate.returncode != 0:
        details = validate.stderr.strip() or validate.stdout.strip() or f"{label} validation failed."
        raise RuntimeError(f"{label} failed validation: {details}")


def run_agent_group(
    *,
    base_dir: Path,
    manifest: dict[str, object],
    args: argparse.Namespace,
    run_dir: Path,
    specs: list[ReviewAgentSpec],
    agent_entries: list[dict[str, object]],
    stage_label: str,
) -> None:
    timeout_seconds = max(args.timeout_minutes, 1) * 60
    heartbeat_seconds = max(args.heartbeat_seconds, 1)
    running: list[RunningAgent] = []

    for spec in specs:
        running.append(
            spawn_agent(
                base_dir=base_dir,
                manifest=manifest,
                args=args,
                run_dir=run_dir,
                spec=spec,
            )
        )
        set_agent_status(agent_entries, spec, status="running", timestamp_field="started_at")

    update_review_manifest(run_dir, review_agents=agent_entries)

    started = time.monotonic()
    pending = list(running)

    while pending:
        # Drain streaming progress from all pending agents
        for agent in pending:
            drain_stream_progress(agent)

        for agent in list(pending):
            returncode = agent.process.poll()
            if returncode is None:
                continue

            # Process exited; save any remaining output
            save_stream_result(agent)
            close_agent(agent)
            pending.remove(agent)

            if returncode != 0:
                set_agent_status(agent_entries, agent.spec, status="failed", timestamp_field="finished_at")
                terminate_agents(pending)
                update_review_manifest(run_dir, review_agents=agent_entries)
                stderr_text = ""
                if agent.stderr_path.exists():
                    stderr_text = agent.stderr_path.read_text(encoding="utf-8", errors="replace").strip()
                detail = stderr_text[-500:] if stderr_text else f"exit status {returncode}"
                raise RuntimeError(f"{agent.spec.label} exited with status {returncode}. {detail}")

            if not agent.artifact_path.exists():
                set_agent_status(agent_entries, agent.spec, status="failed", timestamp_field="finished_at")
                terminate_agents(pending)
                update_review_manifest(run_dir, review_agents=agent_entries)
                raise RuntimeError(f"{agent.spec.label} finished without creating {agent.artifact_path}.")

            set_agent_status(agent_entries, agent.spec, status="completed", timestamp_field="finished_at")
            update_review_manifest(run_dir, review_agents=agent_entries)

        if not pending:
            break

        elapsed = time.monotonic() - started
        if elapsed >= timeout_seconds:
            for agent in pending:
                set_agent_status(agent_entries, agent.spec, status="failed", timestamp_field="finished_at")
            terminate_agents(pending)
            update_review_manifest(run_dir, review_agents=agent_entries)
            raise RuntimeError(f"{stage_label} timed out after {args.timeout_minutes} minutes.")

        heartbeat_at = now_iso()
        detail_parts = []
        for agent in pending:
            detail_parts.append(f"{agent.spec.label}: {agent.latest_progress}")
        review_detail = f"{stage_label}: " + " | ".join(detail_parts)
        update_review_manifest(
            run_dir,
            review_heartbeat_at=heartbeat_at,
            review_detail=review_detail,
            review_agents=agent_entries,
        )
        print(
            f"[runner] {stage_label} still running after {format_elapsed(elapsed)}. {review_detail}",
            flush=True,
        )
        time.sleep(heartbeat_seconds)


def record_usage_summary(run_dir: Path, base_dir: Path) -> Path | None:
    try:
        usage_path = write_run_usage_summary(base_dir, run_dir)
    except Exception:
        return None

    usage = json.loads(usage_path.read_text(encoding="utf-8"))
    totals = dict(usage.get("totals") or {})

    update_review_manifest(
        run_dir,
        usage_summary_path=str(usage_path.resolve()),
        usage_total_tokens=totals.get("total_tokens"),
        usage_input_tokens=totals.get("input_tokens"),
        usage_cached_input_tokens=totals.get("cached_input_tokens"),
        usage_output_tokens=totals.get("output_tokens"),
        usage_estimated_cost_usd=totals.get("estimated_cost_usd"),
    )
    return usage_path


def run_validation_and_apply(base_dir: Path, run_dir: Path) -> Path:
    validate = run_subprocess(
        [sys.executable, str(base_dir / VALIDATE_SCRIPT), "--run-dir", str(run_dir)],
        cwd=base_dir,
        capture_output=True,
    )
    if validate.returncode != 0:
        details = validate.stderr.strip() or validate.stdout.strip() or f"{VALIDATE_SCRIPT} failed."
        raise RuntimeError(details)
    if validate.stdout.strip():
        print(validate.stdout.strip())

    apply = run_subprocess(
        [sys.executable, str(base_dir / APPLY_SCRIPT), "--run-dir", str(run_dir)],
        cwd=base_dir,
        capture_output=True,
    )
    if apply.returncode != 0:
        details = apply.stderr.strip() or apply.stdout.strip() or f"{APPLY_SCRIPT} failed."
        raise RuntimeError(details)

    output = apply.stdout.strip().splitlines()
    if not output:
        raise RuntimeError(f"{APPLY_SCRIPT} did not print the reviewed workbook path.")
    return Path(output[-1]).resolve()


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    run_dir: Path | None = None

    try:
        run_dir = prepare_or_reuse_run(base_dir, args)
        manifest = load_run_manifest(run_dir)
        clear_generated_artifacts(run_dir, manifest)
        staged_support_files = stage_support_files(run_dir, args.support_file)
        if staged_support_files:
            existing_support_files = list(manifest.get("support_files") or [])
            write_run_manifest(
                run_dir,
                {
                    "support_files": existing_support_files + [name for name in staged_support_files if name not in existing_support_files],
                    "input_dir": str((run_dir / "inputs").resolve()),
                },
            )
            manifest = load_run_manifest(run_dir)

        agent_entries = build_agent_manifest(run_dir)
        update_review_manifest(
            run_dir,
            review_status="running",
            review_error=None,
            review_started_at=now_iso(),
            review_finished_at=None,
            review_detail="Preparing the multi-agent workbook review.",
            review_agents=agent_entries,
            reviewed_workbook=None,
        )

        update_review_manifest(
            run_dir,
            review_detail="Running the row reviewer and pattern reviewer in parallel.",
            review_agents=agent_entries,
        )
        run_agent_group(
            base_dir=base_dir,
            manifest=manifest,
            args=args,
            run_dir=run_dir,
            specs=[ROW_REVIEW, PATTERN_REVIEW],
            agent_entries=agent_entries,
            stage_label="Parallel candidate review",
        )

        validate_annotation_artifact(base_dir, run_dir, agent_artifact_path(run_dir, ROW_REVIEW), ROW_REVIEW.label)
        validate_annotation_artifact(base_dir, run_dir, agent_artifact_path(run_dir, PATTERN_REVIEW), PATTERN_REVIEW.label)
        record_usage_summary(run_dir, base_dir)

        update_review_manifest(
            run_dir,
            review_detail="Reconciling candidate reviewers and grouping common issues.",
            review_agents=agent_entries,
        )
        run_agent_group(
            base_dir=base_dir,
            manifest=manifest,
            args=args,
            run_dir=run_dir,
            specs=[RECONCILE_REVIEW],
            agent_entries=agent_entries,
            stage_label="Reconcile review",
        )

        record_usage_summary(run_dir, base_dir)

        annotations_path = run_dir / "annotations.json"
        if not annotations_path.exists():
            raise RuntimeError(f"Automatic review finished without creating {annotations_path}.")

        update_review_manifest(
            run_dir,
            review_detail="Checking the final review file against the workbook and checklist.",
            review_agents=agent_entries,
        )
        reviewed_workbook = run_validation_and_apply(base_dir, run_dir)
        record_usage_summary(run_dir, base_dir)

        update_review_manifest(
            run_dir,
            review_status="reviewed",
            review_error=None,
            review_finished_at=now_iso(),
            review_detail="The reviewed workbook is ready to download.",
            review_agents=agent_entries,
            reviewed_workbook=str(reviewed_workbook),
        )
        print(reviewed_workbook)
    except Exception as exc:  # noqa: BLE001
        if run_dir is not None:
            record_usage_summary(run_dir, base_dir)
            update_review_manifest(
                run_dir,
                review_status="failed",
                review_error=str(exc),
                review_finished_at=now_iso(),
                review_detail="The multi-agent review was interrupted before the workbook was finished.",
            )
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
