# Workbook Review Context

- workbook: `Best-Agency---Transaction-Details-by-Tax-Code-2.xlsx`
- selected sheet: `Transaction Detail by Tax Code`
- transaction rows extracted: `41`
- header row: `5`
- workbook remains source of truth: `yes`
- full row dump generated: `False`

## Tax Codes
- `HST ON`: 25
- `Exempt`: 8
- `GST`: 5
- `Meals and Entertainment`: 3

## Transaction Types
- `Invoice`: 19
- `Expense`: 12
- `Bill`: 9
- `Credit Memo`: 1

## Top Accounts
- `4000 Agency Fees`: 20
- `6100 Advertising & Marketing Expense:6102 Meals and Entertainment`: 5
- `5000 Billable Expense`: 4
- `12002 - Prepaid Media - Google`: 3
- `12001 - Prepaid Media - Facebook`: 2
- `6100 Advertising & Marketing Expense`: 1
- `Cost of Goods Sold`: 1
- `6000 Staff Costs:6001 Salaries`: 1
- `6400 Travel:6402 Flights and Ground Travel`: 1
- `6100 Advertising & Marketing Expense:6101 Marketing Expenses`: 1

## Mixed-Tax Customers
- `Alphabet`: Exempt, GST, HST ON
- `Amazon`: GST, HST ON
- `Hungerhub`: Exempt, Meals and Entertainment
- `T. Spaccio`: Exempt, Meals and Entertainment

## Mixed-Tax Accounts
- `4000 Agency Fees`: Exempt, GST, HST ON
- `6100 Advertising & Marketing Expense:6102 Meals and Entertainment`: Exempt, Meals and Entertainment
- `5000 Billable Expense`: Exempt, HST ON

## Implied Rates By Tax Code
- `HST ON`: 0.130000 (20), 0.129919 (1), 0.129999 (1), 0.130003 (1), 0.130004 (1)
- `Exempt`: 0.000000 (8)
- `GST`: 0.050000 (5)
- `Meals and Entertainment`: 0.064999 (1), 0.065000 (1), 0.065280 (1)
