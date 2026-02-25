# Credit Card Hash-Based Account Matching

## Problem

Credit card imports (PDF/CSV) auto-detect accounts using only `institution + account_type`, which fails when a user has multiple cards from the same bank (e.g., Amex Platinum vs Business Platinum). The brokerage import side already has hash-based matching (commit 79401ad) but credit card imports were never updated.

## Approach

Mirror the brokerage pattern: extract the fullest visible account number from each statement, hash it with SHA256, and use hash-first matching with last4+institution fallback.

## Changes

### 1. PDF Parsers — Extract Account Numbers

Each parser extracts account number info into `metadata`:
- `account_last4`: last 4 digits (display/fallback)
- `account_number_raw`: fullest visible number (for hashing, NOT stored)

| Parser | PDF Format | `account_number_raw` | `account_last4` |
|--------|-----------|---------------------|----------------|
| Amex | "Account Ending 3-41008" | `"341008"` | `"1008"` |
| Chase | "XXXX XXXX XXXX 7340" | `"7340"` | `"7340"` |
| BOA | "Account# 4400 6682 7249 4537" | `"4400668272494537"` | `"4537"` |
| Wells Fargo | TBD | Extract if visible | Extract if visible |
| Capital One | TBD | Extract if visible | Extract if visible |
| Ally Bank | Uses existing account parsing | Existing | Existing |

### 2. CSV Parser

- Capital One CSV: extract last4 from "Card No." column
- Other CSVs: no account number available, leave as `None`

### 3. `import_service._find_existing_account()` — Hash-First Matching

1. If `account_number_raw` available → SHA256 hash → match `account_number_hash`
2. Fallback → `last4 + institution + account_type`
3. No match → create new account

### 4. `import_service._create_account_from_detection()` — Store Hash

Compute and store `account_number_hash` when creating accounts with raw numbers.

### 5. Backfill Hash on Fallback Match

When matched via last4 fallback, backfill hash if missing (same as brokerage).

## What Doesn't Change

- `Account` model — `account_number_hash` column already exists
- `compute_account_hash()` — reuse from `brokerage_import_service.py`
- Frontend — delegates to backend for credit card matching
- No migration needed
