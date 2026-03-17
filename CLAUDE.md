# Sales-Tax Workbook Review Pack

This folder is a self-contained starter pack for running an agent-led, checklist-first sales-tax workbook review.

## First step

Read `WORKSPACE_BRIEF.md` first. Do not try to read every file in this folder up front.

## Default read path

For most runs, read only these:

- `WORKSPACE_BRIEF.md`
- `sales-tax-review-guide.md` (the full checklist with review guidance, workbook signals, and avoid rules)
- the source workbook (xlsx in the run's `inputs/` directory)
- the current run context files:
  - `<run-dir>/context/workbook_summary.md`
  - `<run-dir>/context/workbook_profile.json`
  - `<run-dir>/context/customer_tax_profiles.json`
  - `<run-dir>/context/account_tax_profiles.json`
  - `<run-dir>/context/rate_profiles.json`

Only open these if the review is stuck or needs more nuance:

- `AGENT_REVIEW_METHOD.md`
- `client-checklist-source-map.md`
- `checklist-workbook-coverage.md`

## Status calibration

- use `Review Needed` for any checklist-backed concern that deserves follow-up
- use `Needs More Context` when the workbook alone is not enough to assess the checklist item responsibly
- do not use `Likely Incorrect`

## Output format

Write `annotations.json` matching `review_annotation_schema.json`. The schema requires:

- `source_sheet`, `output_sheet`, `annotation_mode` (must be "inline_columns")
- `row_annotations` array with per-transaction flags
- `pattern_annotations` array for workbook-wide pattern clusters
- optional `unmapped_observations` for useful non-checklist anomalies

## Tool guidance

Use the Read tool to inspect the workbook and context files directly. Use Bash only for running Python validation scripts. The substantive review should come from your own analysis of the data.

## Fast workflow (manual mode)

1. `python3 prepare_review_context.py --run-label <name>`
2. read the default path files listed above
3. review every transaction row, then do a workbook-wide pattern pass
4. produce `<run-dir>/annotations.json` matching `review_annotation_schema.json`
5. `python3 validate_annotations.py --run-dir <run-dir>`
6. `python3 apply_review_annotations.py --run-dir <run-dir>`

Keep all generated files inside the current run directory so one workbook's artifacts do not contaminate another run.
