# Agent Review Method

## Purpose

This file is a deeper method appendix for the review.

Use it when you want more discipline around how to conduct the review or challenge borderline findings.

It is designed to prevent two failure modes:

1. shallow deterministic overfitting
2. vague LLM handwaving

It is not the first file to read in the workspace.

## Core principle

The agent is not being asked to "guess the tax answer."

The agent is being asked to:

1. understand the client's checklist
2. understand the workbook structure
3. identify rows and patterns that deserve review under that checklist
4. explain those findings in a structured, workbook-native way

The main product is row-level flags.

Pattern review is there to support row-level decisions and to explain workbook-wide clusters when that adds value.

The checklist, control library, and any supporting heuristics are there to ground the review.

They are not a substitute for judgment.

## What must stay deterministic

Only these things should be deterministic:

- workbook loading
- workbook row extraction
- output schema
- writing annotations back into Excel

These should not be deterministic:

- whether a row deserves review
- how a checklist item applies to a row
- whether multiple rows form a meaningful pattern
- whether missing context prevents a conclusion

Those are agent judgment tasks.

## Judgment hierarchy

The agent is the reviewer.

Use this hierarchy:

1. client checklist and client-authored intent
2. workbook evidence and workbook-wide patterns
3. optional client support files
4. normalized control library wording and light heuristics
5. nothing else unless explicitly requested

This means:

- heuristics may surface candidates
- control wording may anchor the review
- prior examples may inform pattern recognition

But none of those should settle the conclusion by themselves.

## Role of rules and heuristics

Rules are support tools.

Use them to:

- notice candidate rows faster
- keep the review traceable
- make similar cases easier to compare
- ensure each finding ties back to the checklist

Do not use them to:

- auto-conclude that a row is wrong
- override visible workbook context
- force a checklist item where the fit is weak
- replace the challenge pass

## Review stages

The agent should work in these stages, in order.

### Stage 1: Ground the checklist

Before reviewing any rows, the agent should read:

- `sales-tax-control-library.json`

Use these only if they help resolve uncertainty:

- `client-checklist-source-map.md`
- `checklist-workbook-coverage.md`

Then it should mentally classify the relevant controls for the current run into one of three buckets:

- workbook-evaluable
- workbook-partial
- context-required

This matters because the agent should not force a control into use just because it exists in the library.

### Stage 2: Profile the workbook

Before flagging anything, the agent should read:

- `<run-dir>/context/workbook_summary.md`
- `<run-dir>/context/workbook_profile.json`

If the run explicitly generated a full row dump, the agent may also read:

- `<run-dir>/context/workbook_rows.json`

The workbook remains the source-of-truth record.

The extracted context is there to help the agent review the workbook more efficiently, not to replace the workbook evidence.

The default helper context should stay lightweight.

Persistent row dumps are optional and should be used when they materially help the review.

Each workbook review should live in its own run directory so the agent is not reading stale context from another workbook.

The goal is to understand:

- what tax codes exist in this workbook
- what transaction types exist
- how the workbook is grouped
- which customers appear under multiple tax treatments
- which accounts recur
- whether there are visible workbook conventions

This stage prevents premature flagging.

The goal is not to force the workbook into a single sales-side or ITC-side label if the row evidence is mixed.

### Stage 3: Build row-level candidates

The agent should review each row and ask:

- what kind of row is this?
- what checklist items could plausibly apply?
- what evidence is visible on the row?
- what context is missing?

At this stage, the agent should generate candidate findings, not final findings.

Checklist items, tax-code expectations, account heuristics, and memo cues may help surface those candidates.

They do not decide the final annotation on their own.

### Stage 4: Build pattern-level candidates

The agent should separately review for cross-row patterns such as:

- same customer under multiple tax codes
- same account under inconsistent tax treatment
- recurring vendor or customer anomalies
- repeated exceptions in a category

Pattern-level candidates should be assessed separately from row-level candidates.

Then the agent should decide:

- whether the outlier subset deserves review
- whether both subsets deserve review because the workbook does not responsibly resolve the ambiguity
- or whether the pattern is explainable enough that no formal flag is needed

### Stage 5: Challenge the candidates

This is mandatory.

For each candidate finding, the agent should ask:

- is this really tied to the checklist?
- could this be normal variation within the workbook?
- am I relying on missing facts?
- am I treating the majority case as automatically correct?
- am I overusing prior workbook patterns as universal truth?

If the answer is "yes" to any of those concerns, the agent should downgrade the finding or move it to `Needs More Context`.

### Stage 6: Write final annotations

Only after the challenge stage should the agent produce final annotations.

Every formal annotation must include:

- row number or row list
- checklist ref(s)
- status
- issue summary
- missing context
- suggested next step
- highlight columns

## Anti-overfitting rules

These rules are strict.

### Rule 1

Do not treat a prior reviewed workbook as a training set.

Nothing from a prior workbook should be hardcoded as universal truth.

### Rule 2

Do not turn one example into a rule unless it is checklist-backed.

Example:

- "One customer appears with mixed tax codes" can justify a pattern flag in that workbook.
- It does not justify a universal rule that every client must have one and only one tax code.

### Rule 3

Do not use majority treatment as legal truth.

Majority treatment may justify a consistency review.

It does not prove the minority rows are wrong.

Depending on the row context, the agent may flag the minority subset, both subsets, or neither subset.

### Rule 4

Do not infer facts the workbook does not show.

Examples:

- customer province
- place of supply
- vendor registration status
- staff-event attendance facts

If those are needed, say so.

### Rule 5

Do not promote a reconstructed checklist item above a direct-notes one.

Direct-notes controls should carry more authority than reconstructed controls until the real checklist is available.

### Rule 6

Do not let a heuristic outrank judgment.

Examples:

- a majority tax code pattern does not prove the minority rows are wrong
- an account name does not prove the tax treatment without context
- a memo keyword does not prove the checklist item applies
- a prior workbook outcome does not control the current workbook

## Decision hierarchy for findings

For each possible issue, the agent should ask:

1. Is there a checklist item that clearly applies?
2. Is there workbook evidence supporting the issue?
3. Is the workbook evidence enough by itself?
4. If not, what context is missing?
5. Should this be:
   - `Review Needed`
   - `Needs More Context`
   - or omitted

If the issue is a mixed-treatment pattern, the agent should also ask whether the correct row-level output is:

- flag one subset
- flag both subsets
- or record the pattern without forcing a row-level conclusion

## Recommended status discipline

Use `Review Needed` when:

- checklist mapping is strong
- workbook evidence suggests concern, including cases where the evidence looks fairly strong
- and the row deserves follow-up under the checklist

Typical `Review Needed` examples:

- invoice or credit memo revenue rows using a tax code the checklist clearly treats as disallowed
- purchase-side vendor bills sitting in clearly payroll-like accounts while still claiming ITC tax treatment
- rows with visible tax amounts or implied rates that are materially unreasonable on their face
- exempt or zero-rated purchases that need invoice support
- mixed customer treatment where project, entity, or contract differences could still explain the split
- reimbursement-looking rows where the workbook hints at a problem but does not resolve whether the pass-through treatment is legitimate

Use `Needs More Context` when:

- the checklist item may apply
- but the workbook alone is not enough to assess it responsibly

## Highlighting discipline

Highlight only the fields that materially support the finding.

Do not highlight fields just because they are available.

Preferred logic:

- `Tax Code` for tax-treatment issues
- `Account` for account-driven issues
- `Memo/Description` for narrative or exception issues
- `Name` for customer or vendor consistency issues

## Expected output philosophy

The best output is not the longest output.

The best output is:

- traceable
- checklist-backed
- conservative where evidence is thin
- specific where evidence is strong
- row-focused first and pattern-supported second
- easy for a CPA to review quickly
