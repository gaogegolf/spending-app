# Auto-Import-Fixer Agent Memory

## Known Defects
- See `docs/verification/defects.md` for tracked issues
- DEF-001: Chase parser drops sub-dollar transactions
- DEF-002: BOA parser stores payments with inverted sign
- DEF-003: Duplicate "Ge - Chase Freedom Unlimited" account names

## Account Matching Pitfalls
- Two different people's cards can share same last4 at same institution (e.g., Xinzhu's Aspire and Ge's Surpass both last4=1001 at Amex)
- Fix (2026-02-25): `_find_existing_account` now excludes accounts with a different hash in the last4 fallback
- Accounts without any hash (legacy imports, CSV-only) still match on last4 alone — this is by design

## Classification Pitfalls
- Fix (2026-02-25): Removed bare "PAYMENT" from transfer keyword list — was catching merchant payments (e.g., "US TREASURY PAYMENT") as credit card transfers
- Only "AUTOPAY" and "THANK YOU" now trigger TRANSFER classification in `_default_classification`
- LLM classifier can also misclassify — check `classification_method` column to see which path was used

## Data Cleanup Patterns
- Always back up DB first: `cp backend/spending_app.db backend/spending_app.db.backup-$(date +%Y%m%d)`
- Delete transactions before import_records (FK constraint)
- After cleanup, verify counts: `SELECT COUNT(*) FROM transactions WHERE account_id = '...'`

## PDF Parser Identity Extraction (added 2026-02-25)
- All 8 parsers now extract `account_holder_name` and `card_product_name` into metadata
- Amex: first line = product (strip "p. X/Y" suffix), second line = holder (extract leading ALL CAPS words)
- Capital One: skip "Page X of Y" lines, find line with "|" or "Card"
- Chase Bank: "checking"/"savings" keywords appear around line 22+, not in first 10 lines
- Chase CC / Wells Fargo / BOA: holder name only (product unreliable or unavailable)
- Ally Bank: product = "Spending" or "Savings" from account type text
- Holder name detection: look for 2-3 word ALL CAPS lines, exclude section headers; for mixed lines extract leading caps words

## Useful Debug Snippets
See [debug-snippets.md](./debug-snippets.md) for common investigation queries.
