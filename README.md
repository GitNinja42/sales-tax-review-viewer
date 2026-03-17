# Review Pack Template

This folder is a self-contained starter pack for running an agent-led, checklist-first sales-tax workbook review without relying on chat context.

## What this pack does

- prepares workbook context for an agentic review
- lets the agent do the substantive checklist review
- writes a reviewed workbook with inline review columns
- adds a `Pattern Flags` tab for cross-row issues
- keeps the workflow checklist-first and client-first

The control library and support context in this pack are meant to support the agent. They are not meant to replace the agent's judgment.

## What to drop into `review-inputs/`

- the workbook to review as `.xlsx`
- optionally, the raw client checklist file or checklist spreadsheet if you want to override or refine the baked-in checklist pack
- optionally, any real client support files that were actually provided for the run

## Fast path

If you are running a normal review, the default path is:

1. `python3 prepare_review_context.py --run-label <name>`
2. let the agent read the core files (see `CLAUDE.md` for the default read path)
3. have the agent write `<run-dir>/annotations.json`
4. run:

```bash
python3 validate_annotations.py --run-dir <run-dir>
python3 apply_review_annotations.py --run-dir <run-dir>
```

## Claude CLI path

If Claude CLI is installed and authenticated, you can run the full workflow in one command:

```bash
python3 run_claude_review.py --input-workbook /absolute/path/to/source.xlsx --run-label my-review
```

This runner will:

1. prepare or reuse a run folder
2. run a row reviewer and pattern reviewer in parallel against this workspace
3. run a reconciler that reads both candidate artifacts and writes the final `<run-dir>/annotations.json`
4. write `<run-dir>/usage_summary.json` with per-agent token usage and estimated run cost
5. validate the final annotations
6. write the reviewed workbook back into that same run folder

Useful options:

- `--run-dir <run-dir>` to reuse an already-prepared run
- `--model <model>` to pin a Claude model (e.g. `claude-sonnet-4-6`)
- `--support-file /path/to/file` to stage a checklist or other client support file into that run
- `--heartbeat-seconds <n>` to check for streaming progress updates from Claude
- `--timeout-minutes <n>` to fail a stalled run instead of waiting indefinitely
- `--max-turns <n>` to limit agentic turns per Claude invocation (default: 100)
- `--max-budget-usd <n>` to set a cost ceiling per Claude invocation
- `--include-row-dump` if a difficult run genuinely needs `workbook_rows.json`

The browser UI now uses the same runner automatically after a workbook is uploaded. Manual `annotations.json` upload is still available as a fallback if Claude CLI is unavailable or a run needs intervention.

## Browser UI

```bash
python3 review_ui/server.py --port 8790
```

## Deployment

The current architecture assumes:

- a writable filesystem for per-run folders under `review-output/runs/`
- background subprocess support so the UI can launch `run_claude_review.py`
- an installed and authenticated `claude` CLI on the host

A minimal container path is included:

```bash
docker build -t sales-tax-review-pack .
docker run --rm -p 8790:8790 -e ANTHROPIC_API_KEY=your-key sales-tax-review-pack
```

Notes:

- mount a persistent volume for `/app/review-output` if you want runs to survive container restarts
- if you prefer CLI session auth over API-key auth, provide the container with an authenticated Claude home instead
- the built-in server is suitable for internal tooling and small-team use; if you want internet-facing deployment, put it behind a reverse proxy and persistent storage

## Important limitations

- The `CHK-*` IDs are internal traceability IDs, not client-authored checklist row numbers.
- The pack already includes a distilled checklist layer and can run without a raw checklist file.
- If the real checklist is available, it should be used to replace or tighten the baked-in checklist wording.
- Formal flags should come from the client's checklist and workbook evidence, not from external research.
- The checklist and support context are intended to guide the review, not to substitute for judgment.
- Not every checklist item is fully ascertainable from one workbook alone; see `checklist-workbook-coverage.md`.

## Second-stage documentation

Use this pack for the review run itself. Generate client-facing documentation in a second stage using:

- the reviewed workbook
- the client checklist
- [documentation_agent_prompt.txt](documentation_agent_prompt.txt) (manual prompt, not used by the automated pipeline)

The pack also includes `CLIENT_MANUAL.md` for a human-readable explanation of what the tool does.
