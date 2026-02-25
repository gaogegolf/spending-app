# Import Verifier Agent Memory

## Issuer-Specific Quirks

### Chase
- Fees (annual membership) imported as EXPENSE — combine Purchases + Fees for DB comparison
- Refunds in "Payment, Credits" section are typed INCOME in DB (not TRANSFER)
- **Known bug (DEF-001)**: Sub-dollar transactions ($0.05, $0.76) may be dropped during parsing

### Amex
- Complex cards (Platinum, Business) have sub-cards (e.g., GE GAO authorized user) — all roll into one account
- Fees ($695/$895 annual, late fees) imported as EXPENSE; interest charges also EXPENSE
- Statement credits (Resy, Airline, Digital Entertainment) are negative amounts typed INCOME
- Payments are negative amounts typed TRANSFER
- Business Platinum with Pay Over Time: some purchases may be typed TRANSFER (e.g., Best Buy large purchases)

### Fidelity
- Clean format — returns/refunds listed in "Other Credits" section
- No known quirks

### Capital One
- Annual membership fee ($395) imported as EXPENSE
- Refunds/credits typed INCOME in DB; autopay payments typed TRANSFER

### Wells Fargo / Bilt
- Clean format — payments typed TRANSFER, refunds typed INCOME
- No known quirks

### Bank of America (BOA)
- **Known bug (DEF-002)**: Parser stores payments as POSITIVE TRANSFER amounts (inverted vs all other parsers)
- Compare absolute values for payments, not signed values
- Simple statements — often just 1 purchase or 1 payment per cycle

## Common Discrepancy Causes
1. Sub-dollar transactions dropped during Chase PDF parsing
2. Boundary-date transactions from previous statement imports caught by date range filter
3. Authorized user sub-cards (e.g., GE GAO card) — all charges roll into one account
4. Payments/transfers excluded from net (correct behavior)
5. Statement credits (Amex) reduce the net
6. BOA sign inversion — payments stored as positive TRANSFER

## Net Amount Formula
- Net Amount = -(expenses) + (income). **TRANSFER type is EXCLUDED.**
- Code: `frontend/app/transactions/page.tsx` → `calculateDisplayedTotal()`

## Batch Verification Strategy
1. Start with DB queries — list all imports for the account(s) upfront
2. Batch transaction queries — get all summaries by import_id in one script
3. Then read PDFs — only pages 1-3 (summary is always there)
4. Compare systematically — build a table row per PDF
5. Flag discrepancies immediately — note exact missing transaction details

## Documentation Standards
- Verification reports go in `docs/verification/` with naming: `verification-report-YYYY-MM-DD.md`
- One shared `docs/verification/defects.md` tracking all known defects
- Each defect must have a `**Source**:` link to the verification report that discovered it
- Each verification report must link defect references back to defects.md

## Boundary-Date Duplicate Detection
- Statement periods share boundary dates (e.g., previous closes 12/22, current starts 12/22)
- Query transactions on boundary dates and check `import_id` / `created_at`
- Transactions from older imports caught by date filters = likely duplicates
