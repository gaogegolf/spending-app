# Debug Snippets

## Parse a PDF and inspect output
```python
from app.services.file_parser.pdf_parser import PDFParser
p = PDFParser('/path/to/file.pdf')
r = p.parse()
print(f"format={r.metadata.get('format')}, txns={len(r.transactions)}")
print(f"holder={r.metadata.get('account_holder_name')}, product={r.metadata.get('card_product_name')}")
print(f"last4={r.metadata.get('account_last4')}, raw={r.metadata.get('account_number_raw')}")
for t in r.transactions[:5]:
    print(f"  {t['date']} {t['amount']:>10.2f} {t.get('description_raw','')[:50]}")
```

## Inspect raw PDF text (first page)
```python
import pdfplumber
pdf = pdfplumber.open('/path/to/file.pdf')
text = pdf.pages[0].extract_text()
for i, line in enumerate(text.split('\n')[:20]):
    print(f"[{i}] '{line.strip()}'")
pdf.close()
```

## Find all imports for a filename
```sql
SELECT ir.id, ir.account_id, a.name as account, ir.status, ir.created_at,
       (SELECT COUNT(*) FROM transactions t WHERE t.import_id = ir.id) as txns
FROM import_records ir
LEFT JOIN accounts a ON ir.account_id = a.id
WHERE ir.filename LIKE '%PATTERN%'
ORDER BY ir.created_at;
```

## Simulate account matching
```python
from app.services.import_service import ImportService
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
engine = create_engine('sqlite:///spending_app.db')
with Session(engine) as db:
    svc = ImportService(db, user_id='USER_ID_HERE')
    result = svc._find_existing_account(
        institution='American Express',
        account_type='CREDIT_CARD',
        last4='1001',
        account_number_raw='621001'
    )
    print(f"Matched: {result.name}" if result else "No match — would create new account")
```

## Check classification for a description
```python
desc = "US TREASURY PAYMENT ELKHORN"
keywords_transfer = ['AUTOPAY', 'THANK YOU']
keywords_income = ['SALARY', 'PAYROLL', 'DEPOSIT', 'DIRECT DEP']
print(f"Transfer: {any(k in desc.upper() for k in keywords_transfer)}")
print(f"Income: {any(k in desc.upper() for k in keywords_income)}")
```
