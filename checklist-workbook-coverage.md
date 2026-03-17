# Checklist Workbook Coverage

## Purpose

This file shows which checklist items are reasonably reviewable from one workbook alone and which ones usually need extra files or client context.

## Coverage by control

| Control ID | Title | Workbook alone? | Notes |
|---|---|---|---|
| CHK-001 | QuickBooks exception output | No | Needs the QuickBooks exception or AI review export. |
| CHK-002 | Prior-period change review | No | Needs prior-period exception data or filed/current comparison. |
| CHK-003 | Allowed transaction types in sales population | Yes | Usually inferable from transaction type, account, and tax code. |
| CHK-004 | Out-of-scope item in sales population | Partly | Often inferable from account and memo, but stronger with chart of accounts. |
| CHK-005 | Revenue item uses unexpected tax code | Partly | Strong for obvious `Exempt` revenue rows; stronger with any documented expected customer treatment reference. |
| CHK-006 | Expected customer treatment mismatch | No | Needs a client-provided expected treatment reference or customer jurisdiction context. |
| CHK-007 | Same customer has inconsistent sales tax treatment | Yes | Stronger when the workbook has consistent customer naming or other customer identity context. |
| CHK-008 | Internal invoice and internal credit memo mismatch | Partly | Sometimes visible in memo text; pairing logic usually needs more support. |
| CHK-009 | Journal entry affecting sales tax lines | Partly | Possible if journal rows are visible; stronger with journal backup. |
| CHK-010 | Deposit or reimbursement treated as taxable supply | Partly | Often depends on memo text and policy context. |
| CHK-011 | Provincial overlay mismatch | No | Needs client-specific overlay rules and jurisdiction facts. |
| CHK-012 | Allowed transaction types in ITC population | Yes | Usually inferable from transaction type, account, and tax code. |
| CHK-013 | Out-of-scope item in ITC population | Yes | Often inferable from account names like salaries or owner items. |
| CHK-014 | Zero-rated purchase needs support | Partly | Zero-rated code is visible, but support usually needs vendor country or invoice. |
| CHK-015 | Exempt purchase needs support | Partly | Can flag suspicious exempt rows, but approved exempt categories help a lot. |
| CHK-016 | Freelancer or subcontractor tax review | Partly | Names, account, and memo can suggest this, but invoice and registration status are better. |
| CHK-017 | GST or HST amount reasonability on purchases | Yes | Can be tested against implied rate from workbook values. |
| CHK-018 | Review the Expenses with Meals Tax Code | Yes | Usually inferable from account and tax code. |
| CHK-019 | Review all Staff Events (where less than 6 is held and all employees are invited) | No | Workbook alone usually cannot prove event facts or attendee conditions. |
| CHK-020 | Intercompany or reimbursement purchase review | Partly | Often depends on memo text and supporting context. |
