# Sales Tax Review Pack Manual

## Purpose

This manual explains:

- what the review pack does
- what information it uses
- what the `CHK-*` references mean
- what assumptions were made
- how the reviewed workbook is generated
- what limitations still require CPA or client confirmation

This document is meant to be human-readable and suitable for sharing alongside the script and review pack.

## What this tool is

This pack is an agent-first checklist reviewer.

It prepares a QuickBooks sales-tax workbook for review, lets an agent apply the checklist, and then writes review annotations back into a copied version of the workbook.

It is not a tax engine and it is not trying to determine the final legal tax answer on its own.

The checklist structure and any built-in support context are used to support the review, but the reviewing agent is still expected to exercise judgment.

Its workflow is:

1. create a fresh run folder for the workbook
2. extract workbook context into that run folder
3. let the agent compare workbook rows to a checklist
4. generate row and pattern annotations
5. write those annotations back into the workbook in a structured way

The pack is designed to stay xlsx-first.

It may generate lightweight helper context, but the workbook remains the review record and final deliverable.

Each run is meant to stay isolated so one workbook's helper files, annotations, and reviewed output do not bleed into another workbook's review.

## What this tool is not

This tool does not:

- replace a CPA
- perform independent tax research by default
- assume the workbook alone proves every tax conclusion
- treat every anomaly as an error

The tool is designed to support a review workflow, not to replace the client's judgment.

## What files the tool uses

### Required

- the workbook being reviewed

### Built into the pack

- a normalized checklist file:
  - `sales-tax-control-library.json`
- a checklist provenance file:
  - `client-checklist-source-map.md`
- an agent review method:
  - `AGENT_REVIEW_METHOD.md`
- the review script:
  - `prepare_review_context.py`
  - `validate_annotations.py`
  - `apply_review_annotations.py`

### Optional but helpful

- client checklist file or checklist spreadsheet
- any documented expected customer treatment reference
- any client-provided notes that clarify customer or vendor identity
- tax code descriptions, chart of accounts, or similar support files if they already exist

## Source-of-truth order

The review pack uses this source order:

1. actual client checklist, if provided
2. otherwise the baked-in normalized checklist in the pack
3. workbook evidence
4. optional client-provided support files
5. external tax guidance only if explicitly requested

This means the pack is designed to stay aligned with the client's checklist, not to invent its own tax doctrine.

It also means the pack is designed to help the reviewer think in a structured way, not to auto-decide issues mechanically.

The workbook remains the source-of-truth record for the review.

Any extracted JSON or Markdown context is just a helper layer so the agent can reason over the workbook more efficiently.

## How the reviewed workbook is generated

The process:

1. creates a run directory for the workbook review
2. reads the source workbook
3. extracts lightweight helper context such as workbook summary and profile files into that run directory
4. lets the agent review those files against the checklist using a systematic QA-style guide
5. validates the agent annotations against the workbook and checklist IDs
6. creates a copied review sheet
7. adds review columns to the copied sheet
8. highlights supporting evidence fields
9. creates a `Pattern Flags` tab for cross-row issues when a short workbook-wide summary helps explain why multiple rows were flagged

A full persistent row dump is optional, not the default.

The scripts prepare the evidence and write the output.

The substantive decision about whether something deserves a flag is meant to come from the agent review.

The main product is still the row-level flags in the reviewed workbook.

The `Pattern Flags` tab is secondary support, not a replacement for row-level review.

## Review output columns

The reviewed workbook includes these columns:

- `Review Status`
- `Issue Summary`
- `Checklist Item(s)`
- `Missing Context`
- `Suggested Next Step`

### What they mean

#### Review Status

- `Review Needed`
  - the row or pattern deserves review under the checklist, including cases where the workbook evidence looks strong enough to warrant follow-up
- `Needs More Context`
  - the checklist item may apply, but the workbook alone is not enough to evaluate it responsibly

The reviewed workbook may use distinct fills so a reviewer can scan these statuses quickly.

#### Issue Summary

A plain-language explanation of why the row was flagged.

#### Checklist Item(s)

Human-readable checklist item names showing which checklist ideas the flag ties to.

The underlying annotation file may still use internal `CHK-*` IDs for validation and traceability.

#### Missing Context

Any extra information that would help confirm or reject the flag.

Examples:

- expected customer treatment reference
- vendor invoice
- vendor registration status
- chart of accounts

#### Suggested Next Step

A short suggestion for what a reviewer should do next.

## What `CHK-*` means

`CHK-*` is an internal checklist reference system used inside this review pack.

It was created so every flag could trace back to a specific checklist idea.

Important:

- these are not legal citations
- these are not CRA references
- these are not final client checklist row numbers

They are simply traceability IDs inside this pack.

If the client provides the real checklist in a structured format, these internal IDs should be replaced with the client's actual checklist references.

## CHK reference guide

### System-level controls

- `CHK-001`: QuickBooks exception output
  - Used when a system-generated exception list exists.
- `CHK-002`: Prior-period change review
  - Used when filed-period changes need to be reviewed.

### Sales-tax-collected controls

- `CHK-003`: Allowed transaction types in sales population
  - Used when a row type does not look like the kind of transaction expected in the sales-tax-collected population.
- `CHK-004`: Out-of-scope item in sales population
  - Used when something like a bank transfer, owner contribution, or other non-supply item appears in the sales review population.
- `CHK-005`: Revenue item uses unexpected tax code
  - Used when a revenue row appears to use an unexpected tax code, especially `Exempt`.
- `CHK-006`: Expected customer treatment mismatch
  - Used when the workbook treatment conflicts with a separately documented expected customer treatment reference.
- `CHK-007`: Same customer has inconsistent sales tax treatment
  - Used when the same customer appears across similar revenue rows under multiple tax codes.
- `CHK-008`: Internal invoice and internal credit memo mismatch
  - Used when internal transfers do not preserve tax logic consistently.
- `CHK-009`: Journal entry affecting sales tax lines
  - Used when a journal entry appears in the sales review population.
- `CHK-010`: Deposit or reimbursement treated as taxable supply
  - Used when deposits, reimbursements, or advances appear to be handled as ordinary taxable sales without support.
- `CHK-011`: Provincial overlay mismatch
  - Used only if a client-specific provincial overlay rule is part of the review.

### ITC and purchase-side controls

- `CHK-012`: Allowed transaction types in ITC population
  - Used when the ITC review population contains unexpected transaction types.
- `CHK-013`: Out-of-scope item in ITC population
  - Used when the purchase-side population contains accounts like salaries or other out-of-scope items.
- `CHK-014`: Zero-rated purchase needs support
  - Used when zero-rated treatment is visible but not clearly supported.
- `CHK-015`: Exempt purchase needs support
  - Used when an exempt purchase does not clearly fit an accepted exempt category.
- `CHK-016`: Freelancer or subcontractor tax review
  - Used when the row appears to involve a contractor, freelancer, or subcontractor and needs invoice-level review.
- `CHK-017`: GST or HST amount reasonability on purchases
  - Used when the tax amount does not appear to match the implied rate or needs invoice confirmation.
- `CHK-018`: Review the Expenses with Meals Tax Code
  - Used for meals-tax-code review and related anomalies in meals rows.
- `CHK-019`: Review all Staff Events (where less than 6 is held and all employees are invited)
  - Used only when the row appears to be a staff-event item and the workbook plus context support reviewing it under that checklist condition.
- `CHK-020`: Intercompany or reimbursement purchase review
  - Used when intercompany or reimbursement-like language appears on purchase-side rows.

## What assumptions were baked into the pack

### Assumption 1: checklist-first review

The pack assumes the purpose is to apply the client's checklist, not to produce an independent tax opinion.

### Assumption 2: workbook annotations are the main output

The pack assumes the main deliverable is a reviewed workbook, not a separate JSON file or legal memo.

### Assumption 3: not every control is fully evaluable from one workbook

Some controls can be reviewed well from workbook data alone.

Others need more context.

This is why the pack includes `Missing Context` and allows `Needs More Context`.

### Assumption 4: customer identity may need light normalization

The same customer may appear under slightly different names in the workbook.

The support scripts use basic normalization to catch some of this, but the agent should still verify that the rows appear to refer to the same customer before leaning on a cross-row pattern.

### Assumption 5: internal checklist IDs are acceptable until the real checklist is available

The pack uses `CHK-*` IDs as temporary traceability markers until the actual checklist can be structured more exactly.

## What was used to build the baked-in checklist

The baked-in checklist was distilled from:

- the client's notes

The source map in `client-checklist-source-map.md` shows which items came directly from the notes and which ones required more interpretation.

The actual review loop used by the agent is documented in `AGENT_REVIEW_METHOD.md`.

## What can be reasonably reviewed from one workbook alone

Strong workbook-only checks usually include:

- unexpected transaction types
- mixed tax treatment for the same customer
- obvious out-of-scope accounts
- rate math checks
- meals-tax-code consistency

Controls that often need more context include:

- prior-period changes
- expected customer treatment checks
- provincial overlays
- full staff-event conditions
- vendor registration status

See `checklist-workbook-coverage.md` for a more detailed matrix.

## How evidence highlighting works

The tool highlights fields based on the type of checklist issue.

General rule:

- highlight `Tax Code` when the issue is about the tax treatment itself
- highlight `Account` when the issue is account-driven
- highlight `Memo/Description` when wording on the row matters
- highlight `Name` when the issue is customer or vendor consistency

This means different rows may highlight different fields depending on the checklist item involved.

## How pattern flags work

Some issues are not limited to one row.

Example:

- the same customer appears under multiple tax codes across similar revenue rows

In those cases the pack does two things:

1. annotates the row or rows that actually deserve review
2. adds a summary entry to the `Pattern Flags` tab

The pattern summary is meant to explain the cluster, not replace the row-level decision.

If the workbook clearly points to one suspicious subset, the agent may flag that subset only.

If the workbook shows real inconsistency but does not responsibly resolve which side is wrong, the agent may flag both subsets.

This keeps the workbook usable while still surfacing cross-row issues clearly.

## What to do when the actual checklist becomes available

Once the actual checklist is available in a structured format:

1. replace the internal `CHK-*` mapping with the real checklist structure
2. tighten any wording that was inferred from the notes
3. remove any controls that are not actually part of the checklist
4. add any missing controls from the real checklist

## Recommended operating model

### Step 1

Run the review pack on the workbook.

### Step 2

Have a reviewer inspect:

- all flagged rows, especially `Review Needed` rows
- all `Pattern Flags`

### Step 3

Use a second documentation step to create a client-facing summary of:

- what was reviewed
- which controls were applied
- what was flagged
- what still needs confirmation

## Final note

This pack is designed to be practical, traceable, client-aligned, and agent-driven.

Its main purpose is to make workbook review more structured and repeatable while preserving CPA oversight.
