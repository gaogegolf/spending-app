# Account Detail Page Design

**Goal:** Add a dedicated account detail page at `/accounts/[id]` that shows import history (statements/snapshots) with actions, covering both bank and brokerage account types.

## Routing & Navigation

- New page: `/accounts/[id]`
- Account cards on `/accounts` become clickable links
- Detail page has back link to `/accounts`

## Page Layout

### Header Section (all account types)
- Account name, type icon, institution, last 4 digits
- Edit / Delete buttons
- Active/Inactive status badge

### Bank Accounts (CREDIT_CARD, CHECKING, SAVINGS, CASH, DIGITAL_WALLET, OTHER)

**Summary stats:** total transactions, transaction date range

**Statements table** (from `import_records`):
- Columns: Filename, Source Type (PDF/CSV), Date Imported, Transactions Imported, Status
- Actions: Delete per row
- Sorted by import date descending

**Quick link:** View transactions filtered by this account (links to `/transactions?account_id=<id>`)

### Brokerage Accounts (BROKERAGE, IRA_ROTH, IRA_TRADITIONAL, RETIREMENT_401K, STOCK_PLAN)

**Summary stats:** total value (from latest snapshot), positions count

**Snapshots table** (from `holdings_snapshots`):
- Columns: Statement Date, Total Value, Positions, Reconciliation Status
- Actions: Delete per row
- Sorted by statement date descending

**Statements table** (from `import_records`): same as bank accounts

## API

Use existing endpoints:
- `GET /api/v1/accounts/{id}` — account details + stats
- New: `GET /api/v1/accounts/{id}/imports` — list import records for account
- New: `GET /api/v1/accounts/{id}/snapshots` — list holdings snapshots for account
- Existing: `DELETE /api/v1/imports/{id}` or new delete endpoint for import records
- Existing or new: delete endpoint for snapshots

## Data Flow

1. Page loads → fetch account details + imports + snapshots (parallel)
2. Display appropriate sections based on account type
3. Delete actions → call API → refresh list
