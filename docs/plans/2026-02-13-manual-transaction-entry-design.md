# Manual Transaction Entry

Allow users to manually add transactions beyond what's imported from statements.

## Backend

**New endpoint**: `POST /api/v1/transactions`

- Uses existing `TransactionCreate` schema
- Validates `account_id` belongs to the authenticated user
- Generates deterministic dedup key: `SHA256("manual:{account_id}:{date}:{description_raw}:{amount}")`
- Sets `classification_method = MANUAL`, `import_id = None`
- Calls `set_is_spend_based_on_type()` to derive `is_spend`/`is_income` flags
- Returns `TransactionResponse` on success
- Returns 409 Conflict on duplicate dedup key

No schema changes or migrations required.

## Frontend

**Entry point**: "Add Transaction" button in the Transactions page header, next to "Export CSV" and "Re-classify All".

**Dialog form fields**:

| Field | Required | Input | Default |
|-------|----------|-------|---------|
| Date | Yes | date picker | today |
| Description | Yes | text | - |
| Amount | Yes | number | - |
| Account | Yes | select (user's accounts) | - |
| Type | Yes | select (EXPENSE/INCOME/TRANSFER) | EXPENSE |
| Category | No | select (filtered by type) | - |
| Subcategory | No | text | - |
| Merchant name | No | text | - |
| Note | No | text | - |
| Currency | No | text | USD |

**Behavior**:
- On submit: POST to API, close dialog, reload transaction list
- On 409: show "Duplicate transaction" error inline
- On validation error: show field-level errors

## API Client

Add `createTransaction(data)` to `lib/api.ts` — POST to `/api/v1/transactions`.
