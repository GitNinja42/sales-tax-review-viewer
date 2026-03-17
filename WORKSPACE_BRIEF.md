# Workspace Brief

## Situation

This workspace is for a Canadian sales-tax review workflow built around QuickBooks exports.

The underlying business problem is:

- a CPA or bookkeeping team exports transaction-level sales-tax detail from QuickBooks
- they manually review the workbook against a checklist of concerns
- they want an agent to help perform that review in a structured, repeatable way
- the main deliverable is a reviewed workbook with row-level annotations, with a secondary pattern summary tab when workbook-wide issues need to be surfaced

## What the agent is being asked to do

The agent is not being asked to produce an independent tax opinion.

The agent is being asked to:

- understand the client's checklist and review intent
- inspect the workbook carefully
- review the workbook line by line so each transaction is assessed on its own facts
- review the workbook in totality so patterns, inconsistencies, and outliers are also surfaced
- decide which rows and cross-row patterns deserve review
- treat row-level flags as the main product and use patterns as supporting context
- tie every formal flag to one or more checklist items
- preserve useful workbook-wide anomaly review rather than reducing the job to isolated row checks
- stay conservative when the workbook alone does not prove the answer
- if a mixed-treatment pattern is materially ambiguous, flag both subsets rather than inventing certainty
- allow the workbook to be mixed; do not force the whole sheet into a single sales-side or ITC-side label if the row evidence is mixed
- act like a smart QA reviewer, not a rule engine

## Recommended read order

For the actual review, start with:

1. this file
2. `sales-tax-review-guide.md` (the full checklist with review guidance, workbook signals, and avoid rules)
3. the workbook and any extracted context files

Use these only if needed:

- `client-checklist-source-map.md` for provenance questions
- `checklist-workbook-coverage.md` for workbook-only limits
- `AGENT_REVIEW_METHOD.md` for deeper review discipline

## Source posture

Use sources in this order:

1. actual client checklist, if present
2. otherwise the baked-in checklist in `sales-tax-control-library.json`
3. workbook evidence
4. optional client support files
5. external tax research only if explicitly requested

The workbook remains the source-of-truth record for the review run.

Any extracted JSON or Markdown context is a helper layer for the agent, not a replacement for the workbook itself.

Optional support files are only relevant if they were actually provided for the run.

Do not assume they exist.

## Guardrails

- formal flags must be checklist-backed
- other useful anomalies may be recorded separately as non-checklist observations
- rules and heuristics may help surface candidates, but they do not decide the answer
- the checklist should focus the review, not put the agent on an unnecessarily tight leash
- if workbook evidence is thin, use `Needs More Context` or do not flag
- do not overfit to prior workbooks or prior outputs
- do not assume the majority pattern is automatically correct
- do not pretend the workbook contains customer geography or other context unless the row evidence actually supports that reading

## Main deliverables

- reviewed workbook copy with inline review columns
- `Pattern Flags` tab for workbook-wide issues when it helps explain why multiple rows were flagged

Client-facing explanation can be generated separately after the review run.

## Example output

See `example_annotations.json` for a complete, realistic annotation file showing a row annotation, a pattern annotation, and an unmapped observation.

## What not to flag

Do not flag a row just because the majority of similar transactions use a different tax code. Example: if 9 out of 10 "Office Supplies" transactions use GST and one uses Exempt, that alone is not a flag. The one Exempt transaction might be a legitimate purchase from a non-registered vendor. Flag it only if the workbook evidence (vendor name, amount, memo, account) gives a specific reason to question the treatment.

## Review discipline

- If a control is only weakly supported by the workbook, downgrade the finding or leave it unflagged.
- Row-level flags are the main deliverable. Use patterns to support row-level decisions, not to replace them.
- If a mixed-treatment pattern is strong, the agent may flag one subset or both subsets. If the ambiguity is material, flag both rather than pretending certainty.
- If a pattern spans multiple rows, annotate the rows that deserve review and also create a short pattern summary when it helps explain the cluster.
- Do not force a whole-sheet sales-side or ITC-side classification when the workbook is mixed.
- If a row looks suspicious but does not map cleanly to the checklist, keep it as an observation rather than a formal flag.
- When choosing what to highlight, prefer the field that best supports the control:
  - `Tax Code` for tax-treatment questions
  - `Account` for account-driven concerns
  - `Memo/Description` for narrative or reimbursement clues
  - `Name` for customer or vendor consistency issues

## Troubleshooting

- **No obvious header row**: `prepare_review_context.py` searches for known column headers (e.g. "Tax Code", "Name", "Amount"). If it cannot find one, it will print an error. Check whether the workbook uses non-standard column names and update `workbook_utils.py:find_header_row` if needed.
- **Critical columns missing**: If the workbook lacks "Tax Code" or "Amount" columns, the context extraction will produce empty profiles. The review can still proceed but will be limited. Flag this in annotations using `Needs More Context`.
- **Multiple candidate sheets**: `workbook_utils.py:choose_review_sheet` picks the sheet with the most rows matching tax-detail headers. If the wrong sheet is selected, pass the sheet name explicitly via `--sheet-name`.
- **Validation fails after writing annotations**: Read the validator output carefully. Common causes: `source_row` references a row number that does not exist in the workbook, `checklist_refs` uses a control ID not in `sales-tax-control-library.json`, or `status` uses a value other than "Review Needed" or "Needs More Context".
