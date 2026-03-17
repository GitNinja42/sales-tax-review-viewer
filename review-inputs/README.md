# Review Inputs

Drop the files for a review run here.

Recommended files:

- one `.xlsx` workbook to review
- optionally, the client checklist file or checklist spreadsheet
- optionally, any real client support files that already exist

The preferred flow for this pack is:

1. run `prepare_review_context.py`
2. note the printed run directory under `review-output/runs/`
3. let the agent review that run's extracted context against the checklist
4. run `validate_annotations.py --run-dir <run-dir>`
5. run `apply_review_annotations.py --run-dir <run-dir>`

By default `prepare_review_context.py` writes lightweight helper context only.

If you need a persistent full row dump for debugging, rerun with `--run-dir <run-dir> --include-row-dump`.

Note:

- the pack already includes a baked-in normalized checklist
- the raw client checklist is only needed if you want to override or refine that baked-in checklist
- the preferred path is agent review with `prepare_review_context.py`, `validate_annotations.py`, and `apply_review_annotations.py`
- each workbook review should stay in its own run directory so artifacts do not cross-contaminate future runs
- the workbook remains the source of truth; extracted JSON or Markdown context is just a helper layer
- do not assume support files exist unless they were actually provided for the run
