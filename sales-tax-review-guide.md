# Sales Tax Review Guide

This file is the operational review guide for the checklist. It tells you what each control is trying to catch, what workbook signals matter, and what to avoid.

This is a guide for judgment, not a rule engine.

## How to use this guide

For each control:

1. Decide whether the workbook gives enough evidence to assess it
2. Inspect the most relevant workbook signals
3. Generate candidate findings
4. Challenge those candidates before finalizing them

The checklist is meant to structure the review, not flatten it.

Use workbook-wide comparisons, anomaly clustering, and cross-row consistency when they help you apply the checklist more intelligently.

The intended review flow is:

1. Make a line-by-line pass so each transaction is considered individually
2. Make a whole-workbook pass so recurring patterns and inconsistencies are visible
3. Reconcile those two views before finalizing findings

Workbooks may mix revenue and expense rows on one sheet. Do not force the whole workbook into a single sales-side or ITC-side label if the row evidence is mixed. Use the checklist at the row level first, then use cross-row patterns to decide whether one subset, both subsets, or neither subset deserves a flag.

---

## System controls

### CHK-001: QuickBooks exception output

**What to inspect:** Only use this if a QuickBooks exception export or AI output is present.

**Review question:** Did QuickBooks already flag this transaction as inconsistent in the system-level review?

**Flag when:**
- The row appears on a QuickBooks exception or error list

**Workbook signals:** transaction number, transaction type, tax code

**Avoid:** Inventing a system exception just because a row looks odd.

---

### CHK-002: Prior-period change review

**What to inspect:** Only use this if prior-period change evidence is present.

**Review question:** Was a previously filed period changed, and does the client checklist require review?

**Flag when:**
- A filed-period transaction changed
- Filed amount and current amount no longer agree

**Workbook signals:** date, transaction number, any prior-period exception detail actually provided for the run

**Avoid:** Assuming a date alone proves this is a prior-period adjustment.

---

## Sales-tax-collected controls

### CHK-003: Allowed transaction types in sales population

**What to inspect:** Whether a row that appears to belong in the sales-tax-collected review uses a transaction type the checklist expects.

**Review question:** Is this the kind of row the client expects to sit in the sales-tax-collected review?

**Flag when:**
- This row is an unexpected transaction type for the sales-tax-collected review

**Workbook signals:** transaction type, account, tax code, report section

**Avoid:** Treating every unusual row as wrong if the report definition is unknown.

---

### CHK-004: Out-of-scope item in sales population

**What to inspect:** Rows that look like transfers, owner activity, reimbursements, or non-supply items.

**Review question:** Does this row represent something outside the sales tax regime that should not sit in the sales review?

**Flag when:**
- Owner contributions, bank transfers, cash back, or other non-supply items appear in the sales review population

**Workbook signals:** account, memo or description, transaction type

**Avoid:** Calling something out-of-scope if the memo is too thin to tell.

---

### CHK-005: Revenue item uses unexpected tax code

**What to inspect:** Revenue-like rows where the applied tax code looks unsupported under the checklist.

**Review question:** Does the tax code used on a revenue item make sense under the client checklist?

**Flag when:**
- A revenue row uses Exempt unexpectedly
- A revenue row uses zero-rated or exempt treatment without visible support

**Workbook signals:** account, tax code, transaction type, memo or description

**Avoid:** Assuming one peer pattern proves the correct tax code when the workbook itself does not clearly resolve it.

---

### CHK-006: Expected customer treatment mismatch

**What to inspect:** Differences between workbook treatment and any client-provided expected customer treatment reference, if one exists.

**Review question:** Does the tax code match any documented expected treatment for this customer?

**Flag when:**
- Actual tax code differs from documented expected customer treatment

**Workbook signals:** name, tax code, any row fields that genuinely help identify customer treatment in this workbook

**Avoid:**
- Flagging this from workbook evidence alone when the expected treatment reference is missing.
- Assuming a field like Location is geographic unless the workbook clearly uses it that way.

---

### CHK-007: Same customer has inconsistent sales tax treatment

**What to inspect:** Same customer across similar rows with different tax codes.

**Review question:** Is the same customer receiving multiple tax treatments across similar sales rows?

**Flag when:**
- Same customer appears with inconsistent tax codes across similar revenue rows

**Workbook signals:** normalized customer name, tax code, account, memo or description

**Avoid:**
- Assuming the majority treatment is automatically right.
- Automatically flagging every row in both groups without deciding whether one subset or both subsets actually deserve review.
- Requiring memo, Location, or project labels to match perfectly before surfacing the pattern. If the same normalized customer is on the same revenue account under multiple tax codes, keep it as a real candidate unless the workbook itself clearly explains the split.

---

### CHK-008: Internal invoice and internal credit memo mismatch

**What to inspect:** Internal pairs that should preserve the original tax logic.

**Review question:** Do internal invoice and credit memo pairs preserve the original tax logic and net impact?

**Flag when:**
- Internal invoice or credit memo omits the original tax treatment
- Paired internal transactions do not net logically

**Workbook signals:** memo or description, transaction numbers, tax code, offsetting amounts

**Avoid:** Forcing a pair when the workbook does not clearly show one.

---

### CHK-009: Journal entry affecting sales tax lines

**What to inspect:** Journal entries in the sales review population and whether they seem intentional and supported.

**Review question:** Should this journal entry be affecting the sales review population?

**Flag when:**
- A journal entry appears to impact the sales population

**Workbook signals:** transaction type, account, memo or description, tax amount

**Avoid:** Treating every journal entry as wrong just because it is a journal entry.

---

### CHK-010: Deposit or reimbursement treated as taxable supply

**What to inspect:** Rows that read like reimbursements, advances, deposits, or intercompany pass-throughs.

**Review question:** Is the row really a taxable supply, or a deposit, advance, or reimbursement that should be handled differently under the checklist?

**Flag when:**
- Deposits or reimbursements are treated as normal sales without support

**Workbook signals:** memo or description, account, transaction type, tax code

**Avoid:** Relying on one keyword without the surrounding row context.

---

### CHK-011: Provincial overlay mismatch

**What to inspect:** Only if the client has a documented overlay rule.

**Review question:** Does a client-specific provincial overlay appear to be missing or misapplied based on actual row cues and any provided support?

**Flag when:**
- The client has a documented provincial overlay and the row conflicts with it

**Workbook signals:** tax code, any row fields or client support files that actually encode the relevant treatment

**Avoid:**
- Using general tax knowledge in place of the client overlay.
- Assuming a field called Location is province data when it may mean something else.

---

## ITC and purchase-side controls

### CHK-012: Allowed transaction types in ITC population

**What to inspect:** Whether a row that appears to belong in the ITC review uses a transaction type the checklist expects.

**Review question:** Is this the kind of row the client expects to sit in the ITC review?

**Flag when:**
- This row is an unexpected transaction type for the ITC review

**Workbook signals:** transaction type, account, tax code, report section

**Avoid:** Deciding the report is wrong without understanding the report definition.

---

### CHK-013: Out-of-scope item in ITC population

**What to inspect:** Rows that look like payroll, owner items, or other non-ITC items.

**Review question:** Is this purchase-side row actually eligible to sit in the ITC review population?

**Flag when:**
- Salaries, dividends, owner items, or other out-of-scope items appear in purchase tax review

**Workbook signals:** account, transaction type, tax amount

**Avoid:** Assuming account labels always mean the same thing across clients.

---

### CHK-014: Zero-rated purchase needs support

**What to inspect:** Zero-rated purchase rows that need support to be comfortable.

**Review question:** Is there support for zero-rated treatment on this purchase?

**Flag when:**
- A purchase is coded zero-rated without visible support

**Workbook signals:** tax code, name, memo or description, amount pattern

**Avoid:** Flagging every zero-rated purchase as wrong instead of "needs support."

---

### CHK-015: Exempt purchase needs support

**What to inspect:** Exempt purchase rows where the exempt treatment is not obviously supported by the workbook.

**Review question:** Is this purchase one of the client's accepted exempt categories?

**Flag when:**
- A purchase is coded exempt and does not clearly belong to an accepted exempt category

**Workbook signals:** tax code, account, memo or description, name

**Avoid:** Assuming exempt always means wrong.

---

### CHK-016: Freelancer or subcontractor tax review

**What to inspect:** Contractor-like spend that should be checked against vendor invoice treatment.

**Review question:** Do freelancer or subcontractor purchases have the right tax treatment under the client's checklist?

**Flag when:**
- A row appears to relate to freelancers, directors, contractors, or subcontractors
- The row needs vendor registration or invoice review

**Workbook signals:** name, memo or description, account, tax code

**Avoid:** Treating every person-name vendor as a freelancer without more context.

---

### CHK-017: GST or HST amount reasonability on purchases

**What to inspect:** Whether the tax amount appears mathematically and contextually reasonable.

**Review question:** Does the claimed GST or HST amount appear to agree to the row under the client's checklist?

**Flag when:**
- Implied tax rate does not match the tax code
- The amount appears inconsistent with the net amount

**Workbook signals:** tax code, tax amount, net amount, implied rate

**Avoid:** Treating workbook math as conclusive if the invoice basis may differ.

---

### CHK-018: Review the Expenses with Meals Tax Code

**What to inspect:** Meals-coded rows and nearby meals-related anomalies.

**Review question:** Is the meals and entertainment row using the expected special treatment?

**Flag when:**
- A meals row uses a different tax code than the expected meals treatment

**Workbook signals:** account, tax code, memo or description, recurring vendors

**Avoid:** Flagging meals rows just because they are meals rows. Look for inconsistency or missing review support.

---

### CHK-019: Staff event ITC recovery review

**What to inspect:** Only if the row appears staff-event-related and there is enough context to apply the ITC recovery rule. If the row claims 100% ITC, check whether the exception conditions are visible.

**Review question:** If this staff-event row claims 100% ITC recovery, does the workbook evidence support the conditions for the full recovery exception?

**Flag when:**
- A staff-event row claims 100% ITC (not the 50% meals rate) and the workbook does not clearly show the exception conditions are met
- Reminder to reviewer: 100% ITC on staff events requires that all employees are invited and that the employer holds fewer than 6 such events per year. If the row only claims 50% ITC, the standard meals treatment applies and no flag is needed.

**Workbook signals:** memo or description, account, name, tax code

**Avoid:** Pretending the workbook alone proves attendance or frequency conditions.

---

### CHK-020: Intercompany or reimbursement purchase review

**What to inspect:** Rows that look like reimbursements, internal recharges, or intercompany items on the purchase side.

**Review question:** Is the purchase really an intercompany charge or reimbursement that should be treated differently?

**Flag when:**
- Intercompany or reimbursement language appears and the tax treatment is not obviously supported

**Workbook signals:** memo or description, name, account, tax code

**Avoid:** Collapsing this into CHK-010 automatically. Choose the side of the transaction that matches the row.
