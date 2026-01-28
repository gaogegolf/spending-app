# Quarantine System for Failed Transaction Imports

## Overview

A quarantine system that imports valid transactions while capturing failures for in-app review and retry. This addresses partial imports leaving data in a bad state.

## Problem

When importing a statement with 50 transactions, if 10 fail due to parsing errors (bad date formats, unexpected amount characters), the import either fails entirely or silently skips rows. Users can't easily see what failed or fix it.

## Solution

Import valid transactions normally. Quarantine failed rows in a separate table with error details. Provide a UI to review, edit, and retry quarantined transactions.

---

## Data Model

### New table: `quarantined_transactions`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `import_id` | UUID FK | Links to the import record |
| `account_id` | UUID FK | Target account (nullable if unknown) |
| `user_id` | UUID FK | Owner |
| `raw_data` | JSON | Original row data exactly as parsed |
| `error_type` | ENUM | `PARSE_ERROR`, `VALIDATION_ERROR`, `DUPLICATE` |
| `error_message` | TEXT | Human-readable error details |
| `error_field` | VARCHAR | Which field caused the issue (e.g., "date", "amount") |
| `retry_count` | INT | Number of fix attempts (default 0) |
| `status` | ENUM | `PENDING`, `RESOLVED`, `DISCARDED` |
| `created_at` | TIMESTAMP | When quarantined |
| `resolved_at` | TIMESTAMP | When fixed or discarded |

### Updates to `import_records`

Add columns:
- `transactions_quarantined` (INT) - count of failed rows
- `quarantine_resolved` (BOOLEAN) - true when all quarantined items handled

---

## Import Flow

### Current behavior
1. Parse file → get list of transactions
2. For each transaction: validate → insert into `transactions` table
3. If any error, the whole import may fail or silently skip rows

### New behavior
1. Parse file → get list of raw rows
2. For each row, attempt to transform into a valid transaction:
   - **Success** → insert into `transactions` table
   - **Failure** → insert into `quarantined_transactions` with error details
3. Import always "succeeds" but reports counts: `42 imported, 3 quarantined`
4. Update `import_records` with both counts for history

### Transaction handling
- Wrap the entire import in a database transaction
- Valid transactions commit together (atomic)
- Quarantined rows commit separately (they shouldn't block valid ones)

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/quarantine` | List quarantined transactions (filterable by import_id, status) |
| `GET` | `/api/v1/quarantine/{id}` | Get single quarantined row with full details |
| `PATCH` | `/api/v1/quarantine/{id}` | Update fields (date, amount, description, etc.) |
| `POST` | `/api/v1/quarantine/{id}/retry` | Re-validate and attempt import |
| `POST` | `/api/v1/quarantine/{id}/discard` | Mark as discarded |
| `POST` | `/api/v1/quarantine/bulk-retry` | Retry multiple rows |
| `POST` | `/api/v1/quarantine/bulk-discard` | Discard multiple rows |

### Retry logic
1. Take updated fields from `quarantined_transactions`
2. Run through same validation/transformation pipeline as normal import
3. If valid → insert to `transactions`, update quarantine status to `RESOLVED`
4. If still fails → update `error_message`, increment `retry_count`, keep as `PENDING`

### Response format
```json
{
  "id": "...",
  "status": "RESOLVED",
  "error_message": null,
  "transaction_id": "..."
}
```

---

## UI Design

### Access points
- After import completes: "3 transactions need review" link in the success message
- Import history: Badge showing unresolved quarantine count per import
- New nav item or badge on Imports page: "5 quarantined" indicator

### Review interface
A table showing quarantined transactions with:
- Error indicator highlighting the problem field
- Editable inline fields (date, amount, description)
- Original raw value shown for reference (tooltip or side-by-side)
- Actions per row: "Retry", "Discard", "Edit"

### Workflow
1. User sees: `"12/31/25" could not be parsed as a date`
2. User edits the date field to `2025-12-31`
3. Clicks "Retry" → system re-validates → if valid, moves to `transactions` table
4. Row disappears from quarantine, status updated to `RESOLVED`

### Bulk actions
- "Retry All" - attempt to re-import all pending rows
- "Discard All" - mark remaining as intentionally skipped
- Filter by error type to handle similar issues together

---

## Error Handling

### Duplicate detection during retry
- When retrying a quarantined row, check for duplicates against existing transactions
- If duplicate found, offer choice: "Discard as duplicate" or "Import anyway"

### Import deletion
- If user deletes an import record, cascade delete its quarantined rows
- Prompt: "This will also remove 3 quarantined transactions awaiting review"

### Account changes
- If quarantined row has no `account_id`, require user to select account before retry
- If original account was deleted, show warning and require new account selection

### Re-importing the same file
- Current dedup uses file hash - same file won't re-import
- Quarantined rows are tied to the original import
- User must resolve quarantine first, or delete the import to start fresh

### Stale quarantine cleanup
- Optional: Auto-discard quarantined rows older than 90 days
- Or: Show "old quarantine" warning for items pending > 30 days

---

## Files to Modify

| File | Action |
|------|--------|
| `backend/app/models/quarantined_transaction.py` | CREATE - new model |
| `backend/app/routers/quarantine.py` | CREATE - new API routes |
| `backend/app/services/quarantine_service.py` | CREATE - business logic |
| `backend/app/services/import_service.py` | MODIFY - quarantine failures |
| `backend/alembic/versions/xxx_add_quarantine.py` | CREATE - migration |
| `frontend/app/quarantine/page.tsx` | CREATE - review UI |
| `frontend/app/imports/page.tsx` | MODIFY - add quarantine indicators |

---

## Testing Strategy

### Unit tests
- Quarantine model: create, update status, resolve, discard
- Validation pipeline: verify correct error_type and error_field are captured
- Retry logic: successful retry moves to transactions, failed retry updates error

### Integration tests
- Import file with mixed valid/invalid rows → correct counts in both tables
- Retry quarantined row → appears in transactions, removed from quarantine
- Bulk retry with partial success → some resolve, some remain pending
- Delete import → cascades to quarantined rows

### Test fixtures
- `test_mixed_valid_invalid.csv` - 10 valid, 5 with bad dates, 3 with bad amounts
- `test_all_invalid.csv` - every row has an issue
- `test_duplicate_in_quarantine.csv` - row that becomes duplicate after fix

---

## Out of Scope (YAGNI)

- Auto-fix suggestions (e.g., "Did you mean 2025-12-31?")
- Email notifications for quarantined items
- Scheduled auto-retry
- Transfer linking between accounts (separate feature)
- Statement reconciliation (separate feature)
