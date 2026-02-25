# Credit Card Hash-Based Account Matching — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add SHA256 hash-based account matching to credit card/bank transaction imports, mirroring what brokerage imports already have.

**Architecture:** Extract the fullest visible account number from each PDF/CSV parser into `metadata['account_number_raw']` and `metadata['account_last4']`. Update `import_service.py` to use hash-first matching (reusing `compute_account_hash` from brokerage), with last4+institution fallback. Backfill hash on fallback matches.

**Tech Stack:** Python, FastAPI, SQLAlchemy, pdfplumber, regex

---

### Task 1: Extract `compute_account_hash` into shared utility

**Files:**
- Create: `backend/app/services/account_hash.py`
- Modify: `backend/app/services/brokerage_import_service.py:4,37-40`

Currently `compute_account_hash` lives in `brokerage_import_service.py` (line 37-40). Move it to a shared module so `import_service.py` can also use it.

**Step 1: Create shared module**

Create `backend/app/services/account_hash.py`:

```python
"""Shared account number hashing utility."""

import hashlib


def compute_account_hash(raw_account_number: str) -> str:
    """Compute SHA256 hash of normalized account number.

    Strips dashes, spaces, and uppercases before hashing.
    """
    normalized = raw_account_number.replace("-", "").replace(" ", "").strip().upper()
    return hashlib.sha256(normalized.encode()).hexdigest()
```

**Step 2: Update brokerage_import_service.py to import from shared module**

In `backend/app/services/brokerage_import_service.py`:
- Remove the `import hashlib` (line 4) if no other usage
- Remove the `compute_account_hash` function definition (lines 37-40)
- Add import: `from app.services.account_hash import compute_account_hash`

**Step 3: Verify brokerage imports still work**

Run: `cd backend && ./venv/bin/python -c "from app.services.brokerage_import_service import BrokerageImportService; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/app/services/account_hash.py backend/app/services/brokerage_import_service.py
git commit -m "refactor: extract compute_account_hash into shared module"
```

---

### Task 2: Add account number extraction to Amex PDF parser

**Files:**
- Modify: `backend/app/services/file_parser/pdf_parser.py` — `_parse_amex_statement()` method (lines 353-418)

The Amex PDF shows "Account Ending 3-41008" on the first page. The format is `Account Ending X-XXXXX` where the full visible portion (digits only) should be captured as `account_number_raw`, and the last 4 digits as `account_last4`.

**Step 1: Add account number extraction to `_parse_amex_statement()`**

After the `all_text` extraction (line 375) and before parsing transactions, add:

```python
            # Extract account number from Amex format: "Account Ending 3-41008"
            # Amex shows more than last4 — capture full visible portion for hashing
            account_last4 = None
            account_number_raw = None
            amex_acct_match = re.search(
                r'Account\s+Ending\s+([\d][\d\-]+\d)',
                all_text
            )
            if amex_acct_match:
                raw_with_dashes = amex_acct_match.group(1)  # e.g., "3-41008"
                account_number_raw = raw_with_dashes.replace('-', '')  # "341008"
                account_last4 = account_number_raw[-4:]  # "1008"
```

**Step 2: Include in metadata for both success and failure returns**

Update the metadata dict in all three return statements to include:
```python
'account_last4': account_last4,
'account_number_raw': account_number_raw,
```

The success return (line 398) becomes:
```python
                metadata={
                    'total_transactions': len(transactions),
                    'source': 'pdf',
                    'format': 'amex',
                    'account_last4': account_last4,
                    'account_number_raw': account_number_raw,
                },
```

The failure returns (lines 388 and 415) become:
```python
                    metadata={'format': 'amex', 'account_last4': account_last4, 'account_number_raw': account_number_raw},
```

**Step 3: Verify with real Amex PDF**

Run:
```bash
cd backend && ./venv/bin/python -c "
from app.services.file_parser.pdf_parser import PDFParser
p = PDFParser('/Users/gg/Downloads/2026-02-10.pdf')
r = p.parse()
print('last4:', r.metadata.get('account_last4'))
print('raw:', r.metadata.get('account_number_raw'))
print('institution:', r.detected_institution)
"
```
Expected: `last4: 1008`, `raw: 341008`, `institution: American Express`

**Step 4: Commit**

```bash
git add backend/app/services/file_parser/pdf_parser.py
git commit -m "feat: extract account number from Amex PDF statements"
```

---

### Task 3: Add `account_number_raw` to Chase and BOA PDF parsers

**Files:**
- Modify: `backend/app/services/file_parser/pdf_parser.py` — `_parse_chase_statement()` (lines 685-735) and `_parse_boa_statement()` (lines 1626-1669)

Chase already extracts `account_last4`. We just need to also capture `account_number_raw` (which for Chase is the same as last4 since they only show last 4 digits).

BOA already extracts `account_last4` via regex but shows the full 16-digit card number. We need to capture the full number as `account_number_raw`.

**Step 1: Update Chase parser**

In `_parse_chase_statement()`, after line 701 where `account_last4` is set, add:

```python
            # For Chase, only last 4 digits are visible — raw same as last4
            account_number_raw = account_last4
```

Add `'account_number_raw': account_number_raw` to both metadata dicts (success at line 727, failure at line 713).

**Step 2: Update BOA parser to capture full account number**

In `_parse_boa_statement()`, replace the existing regex (line 1637) to capture the full number:

```python
            # BOA shows full account number: "Account# 4400 6682 7249 4537"
            account_last4 = None
            account_number_raw = None
            full_match = re.search(
                r'Account[#\s]+(?:Number[:\s]+)?(\d{4}\s+\d{4}\s+\d{4}\s+\d{4})',
                all_text
            )
            if full_match:
                account_number_raw = full_match.group(1).replace(' ', '')  # "4400668272494537"
                account_last4 = account_number_raw[-4:]  # "4537"
```

Add `'account_number_raw': account_number_raw` to both BOA metadata dicts (success at line 1665, failure at line 1651).

**Step 3: Verify Chase parser still works**

Run:
```bash
cd backend && ./venv/bin/python -c "
from app.services.file_parser.pdf_parser import PDFParser
# Quick import check
print('PDFParser import OK')
"
```

**Step 4: Commit**

```bash
git add backend/app/services/file_parser/pdf_parser.py
git commit -m "feat: extract account_number_raw from Chase and BOA PDF parsers"
```

---

### Task 4: Add `account_number_raw` to Wells Fargo, Capital One, and Ally Bank PDF parsers

**Files:**
- Modify: `backend/app/services/file_parser/pdf_parser.py` — `_parse_wellsfargo_statement()` (line 975), `_parse_capitalone_statement()` (line 1303), `_parse_allybank_statement()` (line 1845)

For WF and CapOne, we don't have sample PDFs to verify exact formats. Add best-effort regex extraction with safe fallback (None if not found).

**Step 1: Update Wells Fargo parser**

In `_parse_wellsfargo_statement()`, after extracting `all_text` (line 995), add:

```python
            # Try to extract account number
            # WF credit card: "Account Number Ending in: 1234" or similar
            account_last4 = None
            account_number_raw = None
            wf_match = re.search(
                r'(?:Account|Card)\s+(?:Number\s+)?(?:Ending\s+(?:in[:\s]*)?)(\d{4})',
                all_text, re.IGNORECASE
            )
            if wf_match:
                account_last4 = wf_match.group(1)
                account_number_raw = account_last4
```

Add `'account_last4': account_last4, 'account_number_raw': account_number_raw` to both metadata dicts.

**Step 2: Update Capital One parser**

In `_parse_capitalone_statement()`, after extracting `all_text` (line 1324), add:

```python
            # Try to extract account number
            # Capital One: "Account Ending in 1234" or "Card No. ...1234"
            account_last4 = None
            account_number_raw = None
            co_match = re.search(
                r'(?:Account|Card)\s+(?:No\.?\s+)?(?:Ending\s+(?:in[:\s]*)?)(\d{4})',
                all_text, re.IGNORECASE
            )
            if co_match:
                account_last4 = co_match.group(1)
                account_number_raw = account_last4
```

Add `'account_last4': account_last4, 'account_number_raw': account_number_raw` to both metadata dicts.

**Step 3: Update Ally Bank parser**

Ally Bank already extracts account balances with last4 per account in `_extract_allybank_balances()`. For the main metadata, extract the spending account's last4:

In `_parse_allybank_statement()`, after extracting `all_text` (line 1866), add:

```python
            # Extract account last4 from Ally Bank format: "xxxxxx1127"
            account_last4 = None
            account_number_raw = None
            ally_match = re.search(r'x{4,6}(\d{4})', all_text)
            if ally_match:
                account_last4 = ally_match.group(1)
                account_number_raw = account_last4
```

Add `'account_last4': account_last4, 'account_number_raw': account_number_raw` to both metadata dicts.

**Step 4: Commit**

```bash
git add backend/app/services/file_parser/pdf_parser.py
git commit -m "feat: extract account numbers from WF, CapOne, Ally PDF parsers"
```

---

### Task 5: Add `account_number_raw` to CSV parser

**Files:**
- Modify: `backend/app/services/file_parser/csv_parser.py` — `parse()` method (line 85)

Capital One CSV has a "Card No." column with values like "1234" (last 4 digits). Extract it and include in metadata.

**Step 1: Update CSV parser to extract card number**

In the `parse()` method, after `self.detected_bank` is set (line 97), add:

```python
            # Extract account number from CSV if available
            account_last4 = None
            account_number_raw = None
            if self.detected_bank == 'Capital One' and 'Card No.' in self.df.columns:
                # Capital One CSV has "Card No." column with last 4 digits
                card_values = self.df['Card No.'].dropna().unique()
                if len(card_values) > 0:
                    card_no = str(int(card_values[0])) if isinstance(card_values[0], float) else str(card_values[0])
                    account_last4 = card_no[-4:]
                    account_number_raw = account_last4
```

**Step 2: Include in metadata**

Update the success return metadata (line 130) to include:
```python
                metadata={
                    'total_rows': len(self.df),
                    'column_mapping': self.column_mapping,
                    'amount_convention': self.amount_convention,
                    'account_last4': account_last4,
                    'account_number_raw': account_number_raw,
                },
```

**Step 3: Commit**

```bash
git add backend/app/services/file_parser/csv_parser.py
git commit -m "feat: extract account number from Capital One CSV"
```

---

### Task 6: Update `import_service.py` with hash-first matching

**Files:**
- Modify: `backend/app/services/import_service.py` — `_create_account_from_detection()` (line 588) and `_find_existing_account()` (line 646)

This is the core change. Mirror the brokerage pattern: hash-first matching, last4+institution fallback, hash backfill on fallback match, store hash on new account creation.

**Step 1: Add import**

At top of `import_service.py`, add:

```python
from app.services.account_hash import compute_account_hash
```

**Step 2: Update `_create_account_from_detection()` to read `account_number_raw`**

In `_create_account_from_detection()` (line 588), after getting `account_last4` from parse_metadata (line 605), add:

```python
        account_number_raw = parse_metadata.get('account_number_raw')
```

**Step 3: Update `_find_existing_account()` to accept and use raw account number**

Change the signature and body of `_find_existing_account()`:

```python
    def _find_existing_account(
        self,
        institution: str,
        account_type: str,
        last4: Optional[str] = None,
        account_number_raw: Optional[str] = None
    ) -> Optional[Account]:
        """Find an existing account matching institution, type, and optionally last4.

        Uses hash-first matching (SHA256 of account number), then falls back
        to last4 + institution matching.
        """
        user_id = self.user_id
        if not user_id:
            return None

        # Try hash-first matching
        if account_number_raw:
            account_hash = compute_account_hash(account_number_raw)
            account = self.db.query(Account).filter(
                Account.user_id == user_id,
                Account.account_number_hash == account_hash,
                Account.is_active == True
            ).first()
            if account:
                return account

        # Fallback: last4 + institution + account_type
        query = self.db.query(Account).filter(
            Account.user_id == user_id,
            Account.institution == institution,
            Account.account_type == account_type,
            Account.is_active == True
        )

        if last4:
            query = query.filter(Account.account_number_last4 == last4)

        return query.first()
```

**Step 4: Update the caller in `_create_account_from_detection()` to pass raw and backfill hash**

In `_create_account_from_detection()`, update the call to `_find_existing_account()` (line 620):

```python
        existing = self._find_existing_account(
            detected_institution, detected_account_type, account_last4, account_number_raw
        )
        if existing:
            # Backfill hash if missing
            if account_number_raw and not existing.account_number_hash:
                existing.account_number_hash = compute_account_hash(account_number_raw)
                self.db.commit()
            logger.info(f"Found existing account {existing.id} for {detected_institution} {detected_account_type} (last4: {account_last4})")
            return existing.id
```

**Step 5: Store hash when creating new accounts**

In the `Account(...)` constructor call (line 630), add the hash:

```python
        new_account = Account(
            user_id=user_id,
            name=account_name,
            account_type=detected_account_type,
            institution=detected_institution,
            account_number_last4=account_last4,
            account_number_hash=compute_account_hash(account_number_raw) if account_number_raw else None,
            is_active=True
        )
```

**Step 6: Verify import works**

Run:
```bash
cd backend && ./venv/bin/python -c "
from app.services.import_service import ImportService
from app.services.account_hash import compute_account_hash
print('hash:', compute_account_hash('341008'))
print('ImportService import OK')
"
```

**Step 7: Commit**

```bash
git add backend/app/services/import_service.py
git commit -m "feat: add hash-first account matching to credit card imports"
```

---

### Task 7: Update frontend to pass `account_number_raw` in preview response

**Files:**
- Modify: `backend/app/services/import_service.py` — `parse_file()` return (line 237)

The parse response already returns `detected_account_last4`. Also return `account_number_raw` so the frontend preview can show it (and the commit path can use it).

**Step 1: Add `account_number_raw` to parse response**

At line 237, after `detected_account_last4`, add:

```python
                'detected_account_last4': result.metadata.get('account_last4') if result.metadata else None,
                'detected_account_number_raw': result.metadata.get('account_number_raw') if result.metadata else None
```

Also ensure `account_number_raw` is stored in `import_metadata` so `commit_import` can access it:

The `import_metadata` dict (line 204) already stores `parse_metadata` which includes `account_number_raw` from the parser metadata. No change needed — it's already available via `parse_metadata.get('account_number_raw')` in the commit path.

**Step 2: Commit**

```bash
git add backend/app/services/import_service.py
git commit -m "feat: expose account_number_raw in parse response"
```

---

### Task 8: End-to-end test with real Amex PDFs

**Files:** None (manual verification)

**Step 1: Check current account state**

Run:
```bash
cd backend && ./venv/bin/python -c "
from app.database import SessionLocal
from app.models.account import Account
db = SessionLocal()
accounts = db.query(Account).filter(Account.institution == 'American Express', Account.is_active == True).all()
for a in accounts:
    print(f'{a.name}: last4={a.account_number_last4}, hash={a.account_number_hash}')
db.close()
"
```

**Step 2: Test Amex PDF parsing**

Run:
```bash
cd backend && ./venv/bin/python -c "
from app.services.file_parser.pdf_parser import PDFParser
from app.services.account_hash import compute_account_hash
for pdf in ['/Users/gg/Downloads/2026-01-13.pdf', '/Users/gg/Downloads/2026-02-10.pdf']:
    p = PDFParser(pdf)
    r = p.parse()
    raw = r.metadata.get('account_number_raw')
    print(f'{pdf}: last4={r.metadata.get(\"account_last4\")}, raw={raw}, hash={compute_account_hash(raw) if raw else None}')
"
```
Expected: Both show `last4=1008`, `raw=341008`

**Step 3: Set hash on the correct existing account**

If "Xinzhu - Business Platinum" doesn't have a hash yet, manually set it:

```bash
cd backend && ./venv/bin/python -c "
from app.database import SessionLocal
from app.models.account import Account
from app.services.account_hash import compute_account_hash
db = SessionLocal()
# Find the Business Platinum account
acct = db.query(Account).filter(Account.name.contains('Business Platinum')).first()
if acct:
    acct.account_number_hash = compute_account_hash('341008')
    acct.account_number_last4 = '1008'
    db.commit()
    print(f'Updated {acct.name}: hash={acct.account_number_hash[:16]}..., last4={acct.account_number_last4}')
else:
    print('Account not found')
db.close()
"
```

**Step 4: Test import via the web UI**

Start backend and frontend, upload one of the Amex PDFs in auto-detect mode, and verify it matches "Xinzhu - Business Platinum" (not "Xinzhu - Platinum").

**Step 5: Commit (if any manual DB fix was needed)**

No code commit needed — this is verification only.
