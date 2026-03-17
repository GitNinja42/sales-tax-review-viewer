# Client Checklist Source Map

## Purpose

This file keeps the control library anchored to the client's notes.

It answers:

- which controls came directly from the notes
- which controls came from the narrative notes
- which controls are still reconstructed or inferred

This should be the reference the team uses when tightening the control library against the real checklist.

## Status labels

- `direct-notes`: reflected directly in the notes taken
- `notes-derived`: described in the narrative notes but not clearly visible as checklist text
- `reconstructed`: inferred from the notes and should be confirmed against the real checklist

## Source map

| Control ID | Status | Near-verbatim client wording or source note |
|---|---|---|
| CHK-001 | notes-derived | Run the Sales Tax AI in the Sales Tax Module in QuickBooks Online which tests the sales tax code applied vs transaction type. |
| CHK-002 | direct-notes | Review the Exception Report to understand whether the changes made to transactions in prior period that was filed is reasonable. If not correct them. |
| CHK-003 | direct-notes | Review the "Transaction Type" in "Transaction Detail with Tax Code Report" to ensure there are only invoices and credit memos transactions reported in line 101 and 103. |
| CHK-004 | direct-notes | Review to ensure there are no transactions included in line 101 and 103 that do not fall in the Sales Tax Regime. |
| CHK-005 | direct-notes | Review tax rate applied to all "Invoice" and "Credit Memo" transactions ... There should be no "Exempt" Tax Code used. |
| CHK-006 | notes-derived | QB will tell me what is a sales tax code we charged and what is the default, and it'll highlight anything that is off. |
| CHK-007 | reconstructed | Same customer has mixed tax treatments across similar revenue rows. This is consistent with the client's comments but not shown as a standalone checklist line. |
| CHK-008 | direct-notes | For any internal transfers ... ensure that the internal invoice and internal credit memo includes the original sales tax code and the net impact is found, highlight and correct. |
| CHK-009 | direct-notes | Review any journal entries that is recorded in line 101. Does it have 103 impact? Why is this done via journal entry? |
| CHK-010 | direct-notes | Intercompany Transactions ... Is this a reimbursement ... if so this is outside of sales tax regime. |
| CHK-011 | notes-derived | BC PST overlay was discussed in the notes, but the exact checklist wording is not clearly visible. |
| CHK-012 | direct-notes | Review the "Transaction Type" in "Transaction Detail with Tax Code Report" to ensure there are only Bills, Expenses, Supplier Credit ... reported in line 106. |
| CHK-013 | direct-notes | Review the Expenses to ensure there are no transactions included in line 106 that do not fall in the Sales Tax Regime. |
| CHK-014 | direct-notes | Review the Expenses with Zero Rated Tax Code. |
| CHK-015 | direct-notes | Review the Expenses with Exempt Tax Code. |
| CHK-016 | direct-notes | Freelancer/Subcontractors ... verify tax code and amount claimed to ensure it agrees to the tax amount on the vendor invoice. |
| CHK-017 | direct-notes | Review the Expenses with HST Tax Code ... ensure we have claimed the correct ITC. Review the Expenses with GST Tax Code ... ensure we have claimed the correct ITC. |
| CHK-018 | direct-notes | Review the Expenses with Meals Tax Code - Sample 10 largest vendors ... ensure we have claimed the correct ITC by opening up the receipt and review. |
| CHK-019 | direct-notes | Review all Staff Events (where less than 6 is held and all employees are invited) to verify that the non-meals tax rate was applied. |
| CHK-020 | direct-notes | Intercompany Transactions / reimbursement language appears in the notes, but the exact purchase-side wording should be confirmed against the real checklist. |

## Practical rule

When the agent is running a workbook review:

- if a control is `direct-notes`, it is safe to use as a checklist-backed control
- if a control is `notes-derived`, it is usable but should be treated as secondary until confirmed
- if a control is `reconstructed`, it should be treated carefully and called out as inferred rather than direct

## Next upgrade

Once the client sends the actual checklist file, replace this source map with:

- exact checklist row numbers
- exact checklist wording
- any control-specific examples or exception lists
