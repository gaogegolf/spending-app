# Personal Finance Management App

A full-stack web application for personal finance management that imports credit card and bank statements (CSV/PDF), automatically classifies transactions using AI, and provides accurate spending analytics with visual dashboards.

**Built with FastAPI, Next.js, SQLAlchemy, and Claude AI.**

## Key Features

### Import & Processing
- **Multi-Format Support**: Import CSV files and PDF statements (Fidelity fully supported)
- **Smart Column Detection**: Automatically detects date, amount, and description columns in CSV files
- **AI-Powered Classification**: Uses Claude AI to intelligently categorize transactions
- **Duplicate Prevention**: Hash-based deduplication prevents re-importing the same transactions
- **Multi-Step Import Wizard**: Upload → Preview → Commit workflow with error handling

### Analytics & Insights
- **Real-Time Dashboard**: View monthly spending, income, and net totals at a glance
- **Category Breakdown**: See spending distribution across categories with visual progress bars
- **Transaction Filtering**: Filter by account, type, category, and review status
- **Accurate Calculations**: Correctly excludes payments and transfers from spending totals

### Data Management
- **Transaction List**: Paginated table view with sorting and filtering
- **Account Management**: Track multiple credit cards and bank accounts
- **User Rules**: Create custom classification rules (future enhancement)
- **Review Queue**: Flag transactions that need manual review

### Technical Excellence
- **Business Rule Validation**: Enforces financial logic (payments ≠ spending)
- **Privacy First**: Only sends necessary data to AI (no personal info)
- **Fast & Responsive**: Next.js frontend with Tailwind CSS
- **RESTful API**: Clean API design with Pydantic validation

## Critical Business Logic

The app implements strict business rules to ensure accurate financial tracking:

✅ **PAYMENT** transactions (credit card payments) → `is_spend=false`
✅ **TRANSFER** transactions (moving money between accounts) → `is_spend=false`
✅ **INCOME** transactions (salary, paycheck) → `is_income=true`, `is_spend=false`
✅ **REFUND** transactions (returns) → `is_spend=false`
✅ **FEE_INTEREST** transactions (fees, interest) → `is_spend=true`
✅ **EXPENSE** transactions (purchases) → `is_spend=true`

**Total Spending = SUM(transactions WHERE is_spend=true)**

## Project Structure

```
spending-app/
├── backend/                          # Python FastAPI backend
│   ├── app/
│   │   ├── models/                   # SQLAlchemy models
│   │   │   ├── account.py           # Account model
│   │   │   ├── transaction.py       # Transaction model (core)
│   │   │   ├── import_record.py     # Import history
│   │   │   └── rule.py              # User rules
│   │   ├── schemas/                  # Pydantic validation schemas
│   │   │   ├── account.py
│   │   │   ├── transaction.py
│   │   │   ├── import_record.py
│   │   │   ├── rule.py
│   │   │   └── stats.py
│   │   ├── services/
│   │   │   ├── file_parser/
│   │   │   │   ├── csv_parser.py    # CSV import with column detection
│   │   │   │   └── pdf_parser.py    # Fidelity PDF parser with text extraction
│   │   │   ├── classifier/
│   │   │   │   ├── llm_classifier.py # Claude API classification
│   │   │   │   ├── rule_engine.py    # User rule matching
│   │   │   │   └── prompts.py        # LLM prompts
│   │   │   ├── import_service.py     # Import orchestration
│   │   │   ├── deduplication.py      # Hash-based dedup
│   │   │   └── stats_service.py      # Spending calculations
│   │   ├── api/v1/                   # REST API endpoints
│   │   │   ├── accounts.py
│   │   │   ├── transactions.py
│   │   │   ├── imports.py
│   │   │   └── stats.py
│   │   ├── main.py                   # FastAPI app
│   │   ├── config.py                 # Configuration
│   │   └── database.py               # Database setup
│   ├── alembic/                      # Database migrations
│   ├── requirements.txt
│   └── .env.example
├── frontend/                         # Next.js 16+ frontend
│   ├── app/
│   │   ├── page.tsx                 # Dashboard with stats cards
│   │   ├── layout.tsx               # Root layout with navigation
│   │   ├── globals.css              # Global styles
│   │   ├── imports/
│   │   │   └── page.tsx            # Import wizard
│   │   └── transactions/
│   │       └── page.tsx            # Transaction list with filters
│   ├── lib/
│   │   ├── api.ts                   # Backend API client
│   │   └── types.ts                 # TypeScript interfaces
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.js               # API proxy configuration
│   └── tailwind.config.ts
└── README.md

## Quick Start Guide

### Prerequisites

- **Python 3.9+** (for backend)
- **Node.js 18+** (for frontend)
- **Anthropic API key** - Get one free at https://console.anthropic.com/
- Optional: PostgreSQL (default uses SQLite)

### Installation & Setup

#### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Initialize database
alembic upgrade head

# Start backend server
uvicorn app.main:app --reload
```

Backend will be running at **http://localhost:8000**

#### 2. Frontend Setup

```bash
# Open a new terminal window
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend will be running at **http://localhost:3000**

### Access the Application

1. **Open your browser** and go to http://localhost:3000
2. **Dashboard**: View your monthly spending stats and category breakdown
3. **Import Page**: Upload CSV or PDF files from your bank
4. **Transactions**: Browse and filter all imported transactions

**That's it!** You're ready to start managing your finances.

## How to Use

### 1. Create an Account
Before importing transactions, you need to create at least one account.

**Via API:**
```bash
curl -X POST http://localhost:8000/api/v1/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Chase Sapphire",
    "institution": "Chase",
    "account_type": "CREDIT_CARD",
    "account_number_last4": "1234",
    "currency": "USD"
  }'
```

**Via Frontend:**
Currently accounts must be created via API. Frontend account creation coming soon.

### 2. Import Transactions

**Option A: Via Frontend (Recommended)**
1. Go to http://localhost:3000/imports
2. Select your account from the dropdown
3. Upload a CSV or PDF file
4. Wait for processing (LLM classification happens automatically)
5. View the import summary

**Option B: Via API**
```bash
# Upload file
curl -X POST http://localhost:8000/api/v1/imports/upload \
  -F "file=@/path/to/statement.pdf" \
  -F "account_id=your-account-id"

# Parse the file
curl -X POST http://localhost:8000/api/v1/imports/{import_id}/parse

# Commit to database
curl -X POST http://localhost:8000/api/v1/imports/{import_id}/commit
```

### 3. View Your Dashboard
- Navigate to http://localhost:3000
- See monthly spending totals, income, and net
- View category breakdown with percentages
- Filter by account if you have multiple

### 4. Browse Transactions
- Go to http://localhost:3000/transactions
- Filter by account, type, category, or review status
- Transactions are color-coded:
  - **Red amounts**: Spending (is_spend=true)
  - **Green amounts**: Income (is_income=true)
  - **Gray amounts**: Payments, transfers, refunds

### 5. Review Classifications
Transactions marked with "Review" badge may need attention:
- Low confidence classifications
- Unusual patterns
- First-time merchants

## API Documentation

When the backend is running, visit **http://localhost:8000/docs** for interactive API documentation (Swagger UI).

### Key Endpoints

**Accounts**
- `GET /api/v1/accounts` - List all accounts
- `POST /api/v1/accounts` - Create new account
- `GET /api/v1/accounts/{id}` - Get account details

**Imports**
- `POST /api/v1/imports/upload` - Upload CSV/PDF file
- `POST /api/v1/imports/{id}/parse` - Parse uploaded file
- `POST /api/v1/imports/{id}/commit` - Commit transactions to database
- `GET /api/v1/imports/{id}` - Get import status

**Transactions**
- `GET /api/v1/transactions` - List transactions with filters
  - Query params: `account_id`, `start_date`, `end_date`, `transaction_type`, `category`, `needs_review`, `page`, `page_size`
- `PUT /api/v1/transactions/{id}` - Update transaction

**Statistics**
- `GET /api/v1/stats/monthly` - Monthly summary
  - Query params: `year`, `month`, `account_id` (optional)

## Technology Stack

### Backend
- **Framework**: FastAPI (Python 3.9+)
- **Database**: SQLAlchemy ORM with SQLite (PostgreSQL optional)
- **Migrations**: Alembic
- **AI/ML**: Anthropic Claude API for transaction classification
- **File Parsing**:
  - `pandas` for CSV processing
  - `pdfplumber` for PDF extraction
- **Validation**: Pydantic schemas

### Frontend
- **Framework**: Next.js 16+ (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS 4.x
- **State Management**: React hooks
- **API Integration**: Fetch API with Next.js rewrites proxy

### Key Libraries
- `anthropic` - Claude AI API client
- `sqlalchemy` - Database ORM
- `pdfplumber` - PDF text/table extraction
- `pandas` - CSV data processing

## Database Schema

### Accounts Table
Stores credit cards and bank accounts.

```sql
id, user_id, name, institution, account_type (CREDIT_CARD|CHECKING|SAVINGS),
currency, is_active, created_at, updated_at
```

### Transactions Table (Core)
Stores all financial transactions with classification.

```sql
id, account_id, import_id, hash_dedup_key (UNIQUE),
date, description_raw, merchant_normalized, amount, currency,
transaction_type (EXPENSE|INCOME|TRANSFER|PAYMENT|REFUND|FEE_INTEREST),
category, subcategory, tags,
is_spend (BOOLEAN), is_income (BOOLEAN),  # CRITICAL FLAGS
confidence, needs_review, matched_rule_id, classification_method,
user_note, metadata, created_at, updated_at
```

### Import Records Table
Tracks import history for deduplication.

```sql
id, account_id, source_type (CSV|PDF), filename, file_hash,
status, error_message, transactions_imported, transactions_duplicate,
metadata, created_at, completed_at
```

### Rules Table
User-defined classification rules.

```sql
id, user_id, rule_type, pattern, action (JSON),
priority, is_active, match_count, name, description,
created_at, last_matched_at
```

## File Format Support

### Fidelity Rewards Visa (PDF)
✅ **Fully Supported**

- Two-table format: "Payments and Other Credits" + "Purchases and Other Debits"
- Handles "CR" suffix on amounts
- Cleans merchant descriptions (removes phone numbers and state codes)
- Example: "COMCAST / XFINITY 800-266-2278 CA" → "COMCAST / XFINITY"

**Test with your Fidelity statements**:
```python
from app.services.file_parser.pdf_parser import PDFParser

parser = PDFParser("/Users/I858764/Documents/Spending/Fidelity® Rewards Visa Signature® Card/2025-11-24 Statement - Card...4855.pdf")
result = parser.parse()

print(f"Success: {result.success}")
print(f"Transactions: {len(result.transactions)}")
print(f"Expected spending: $428.00 (excludes $373 payment + $355 refund)")
```

### CSV Files
✅ **Fully Supported** with automatic column detection

**Features**:
- Auto-detects date, description, and amount columns
- Handles multiple amount conventions:
  - Single column with +/- (negative = expense)
  - Separate debit/credit columns
  - Positive = expense convention
- Column mapping wizard for ambiguous files

## Usage Examples

### 1. Parse a Fidelity PDF Statement

```python
from app.services.file_parser.pdf_parser import PDFParser

parser = PDFParser("path/to/statement.pdf")
result = parser.parse()

if result.success:
    for txn in result.transactions:
        print(f"{txn['date']}: {txn['merchant_normalized']} - ${txn['amount']}")
        print(f"  Is Credit: {txn['is_credit']}")
else:
    print(f"Errors: {result.errors}")
```

### 2. Parse a CSV Statement

```python
from app.services.file_parser.csv_parser import CSVParser

# Auto-detect columns
parser = CSVParser("path/to/statement.csv")
format_info = parser.detect_format()
print(f"Detected columns: {format_info['suggested_mapping']}")
print(f"Confidence: {format_info['confidence']}")

# Parse with detected mapping
result = parser.parse()
print(f"Transactions: {len(result.transactions)}")
```

### 3. Classify Transactions with Claude

```python
from app.services.classifier.llm_classifier import LLMClassifier

classifier = LLMClassifier()
transactions = [
    {"date": "2025-11-14", "description_raw": "COMCAST / XFINITY", "amount": 73.00},
    {"date": "2025-11-17", "description_raw": "PAYMENT THANK YOU", "amount": 373.00},
]

classifications = classifier.classify_batch(transactions)

for cls in classifications:
    print(f"Type: {cls['transaction_type']}, is_spend={cls['is_spend']}")
    # CRITICAL: "PAYMENT THANK YOU" will have is_spend=False
```

### 4. Generate Transaction Hash for Deduplication

```python
from app.services.deduplication import DeduplicationService

txn_data = {
    "account_id": "acct-123",
    "date": "2025-11-14",
    "amount": 73.00,
    "description_raw": "COMCAST / XFINITY"
}

hash_key = DeduplicationService.generate_hash(txn_data)
print(f"Hash: {hash_key}")  # Same transaction = same hash
```

### 5. Calculate Monthly Spending

```python
from app.services.stats_service import StatsService
from app.database import SessionLocal

db = SessionLocal()
stats = StatsService(db)

# Get November 2025 summary
summary = stats.get_monthly_summary(2025, 11)

print(f"Total Spend: ${summary['total_spend']:.2f}")  # Excludes payments/transfers
print(f"Total Income: ${summary['total_income']:.2f}")
print(f"Net: ${summary['net']:.2f}")

for cat in summary['category_breakdown']:
    print(f"  {cat['category']}: ${cat['amount']:.2f} ({cat['percentage']:.1f}%)")
```

## Testing

### Run Tests
```bash
pytest backend/app/tests -v --cov
```

### Test Fidelity PDF Parsing
```bash
python -c "
from app.services.file_parser.pdf_parser import PDFParser

parser = PDFParser('/Users/I858764/Documents/Spending/Fidelity® Rewards Visa Signature® Card/2025-11-24 Statement - Card...4855.pdf')
result = parser.parse()

print(f'Success: {result.success}')
print(f'Transactions: {len(result.transactions)}')

for txn in result.transactions:
    print(f\"  {txn['date']}: {txn['description_raw']} - ${txn['amount']} (credit={txn['is_credit']})\")

# Expected:
# - 4 transactions total
# - 2 credits (payment + refund)
# - 2 debits (purchases)
# - Correct spending: $428.00 (2 purchases only)
"
```

## Key Design Decisions

### Why is_spend Flag?
The `is_spend` boolean flag is the **single source of truth** for spending calculations.
- ✅ Payments to credit cards are NOT spending (money moving, not spent)
- ✅ Transfers between accounts are NOT spending (internal movement)
- ✅ Refunds are NOT spending (money coming back)
- ✅ Only actual purchases and fees count as spending

### Why LLM Validation?
The backend **always validates** LLM output against business rules:
```python
# Even if LLM says PAYMENT has is_spend=true, we force it to false
if transaction_type in ['PAYMENT', 'TRANSFER']:
    classification['is_spend'] = False
```

### Why Hash-Based Deduplication?
Hash is based on: account_id + date + amount + normalized_description
- Same transaction imported twice → same hash → skipped
- Protects against accidental re-imports

## Development Status

### ✅ Completed (MVP Ready!)
**Backend**
- [x] Project structure and configuration
- [x] SQLAlchemy models with proper relationships
- [x] Alembic database migrations
- [x] Pydantic schemas for request/response validation
- [x] CSV parser with auto column detection
- [x] PDF parser for Fidelity format with text extraction fallback
- [x] LLM classifier with Claude API integration
- [x] Business rule validation (PAYMENT/TRANSFER exclusion)
- [x] Rule engine for user-defined rules
- [x] Deduplication service (hash-based)
- [x] Statistics service with accurate spending calculation
- [x] Import orchestrator (upload → parse → classify → commit)
- [x] REST API endpoints:
  - [x] Accounts API (create, list, get)
  - [x] Imports API (upload, parse, commit, status)
  - [x] Transactions API (list with filters, update)
  - [x] Stats API (monthly summary, category breakdown)

**Frontend**
- [x] Next.js 16+ project with TypeScript
- [x] Tailwind CSS 4.x styling
- [x] API client library with proxy configuration
- [x] Dashboard page with stats cards and category breakdown
- [x] Import wizard with multi-step flow
- [x] Transactions list with filters and pagination
- [x] Responsive design for mobile/tablet/desktop

**Testing & Validation**
- [x] End-to-end testing with real Fidelity PDF
- [x] Verified spending calculation ($428.00 correct)
- [x] API integration testing
- [x] Frontend-backend integration verified

### 🚧 Future Enhancements (Post-MVP)
- [ ] Transaction editing UI with inline forms
- [ ] Rules management page (create, edit, delete rules)
- [ ] Charts and visualizations (trend lines, pie charts)
- [ ] Date range filters for custom periods
- [ ] Bulk transaction operations
- [ ] CSV export functionality
- [ ] Docker Compose for one-command deployment
- [ ] Comprehensive unit/integration test suite
- [ ] Multi-user support with authentication (JWT)
- [ ] Production deployment guide (AWS/Heroku/Railway)

## Privacy & Security

- **No Sensitive Data**: Never stores full account numbers or SSNs
- **LLM Privacy**: Only sends date/description/amount to Claude API (no names, addresses)
- **File Cleanup**: Uploaded PDFs are deleted after import (configurable)
- **Local by Default**: SQLite database stays on your machine

## Troubleshooting

### Backend Issues

**PDF Parsing Fails**
- If PDF parsing fails, the error message will suggest downloading CSV from your bank
- Most banks offer CSV export which is more reliable than PDF
- Fidelity PDFs are fully supported with text extraction fallback

**LLM Classification Incorrect**
- Create a user rule to override automatic classification (future feature)
- For now, manually update transactions via the API
- Rules will take priority over LLM when implemented

**Spending Total Wrong**
Check for transactions with incorrect `is_spend` flag:
```sql
-- Find payments/transfers marked as spending (BUG)
SELECT * FROM transactions
WHERE transaction_type IN ('PAYMENT', 'TRANSFER')
AND is_spend = TRUE;

-- These should all have is_spend = FALSE
```

**Database Migration Errors**
```bash
# Reset database if needed
cd backend
rm spending_app.db
alembic upgrade head
```

### Frontend Issues

**Frontend Won't Start**
```bash
# Clear node_modules and reinstall
cd frontend
rm -rf node_modules package-lock.json
npm install
npm run dev
```

**API Calls Failing (CORS/Connection)**
- Make sure backend is running on http://localhost:8000
- Check Next.js proxy configuration in `next.config.js`
- Verify no other services are using port 3000 or 8000

**Dashboard Shows No Data**
- Import transactions first via the Import page
- Check that transactions exist: `curl http://localhost:8000/api/v1/transactions`
- Verify you're viewing the correct month/year

**"Failed to fetch" Errors**
- Ensure both backend (port 8000) and frontend (port 3000) are running
- Check browser console for detailed error messages
- Try accessing backend API directly: http://localhost:8000/docs

### Common Setup Issues

**Missing Anthropic API Key**
```bash
# Backend .env file must have:
ANTHROPIC_API_KEY=sk-ant-xxxxx

# Get a free API key from:
# https://console.anthropic.com/
```

**Port Already in Use**
```bash
# Find and kill process using port 8000
lsof -ti:8000 | xargs kill -9

# Or use a different port
uvicorn app.main:app --reload --port 8001
```

## What Makes This Project Unique

### Accurate Financial Logic
Unlike many finance apps, this project correctly distinguishes between:
- **Spending** (actual purchases that reduce wealth)
- **Payments** (moving money, not spending it)
- **Transfers** (internal movements between accounts)
- **Income** (money coming in)

Many apps incorrectly count credit card payments as spending, leading to double-counting.

### AI-Powered with Business Rules
The LLM provides intelligent categorization, but **business rules always win**:
- Even if Claude classifies a payment as spending, the backend enforces `is_spend=false`
- Guarantees accurate spending totals regardless of AI errors
- Best of both worlds: AI flexibility + rule-based accuracy

### Real-World PDF Support
- Handles actual bank statements (Fidelity format fully tested)
- Text extraction fallback when table parsing fails
- Cleans merchant names (removes phone numbers, addresses)
- Multi-line description support for complex transactions

### Privacy-Focused Design
- Only minimal data sent to Claude API (date, description, amount)
- No names, addresses, or full account numbers ever leave your machine
- SQLite database stored locally by default
- Upload files deleted after processing

### Developer-Friendly
- Clean separation of concerns (parsers, classifiers, validators)
- Comprehensive error handling with helpful messages
- RESTful API with OpenAPI documentation
- Type-safe with Pydantic and TypeScript

## Project Goals

This project was built to:
1. **Solve a real problem**: Accurately track spending across multiple accounts
2. **Demonstrate LLM integration**: Show how to combine AI with business rules
3. **Handle real-world data**: Parse actual bank PDFs, not just clean CSVs
4. **Follow best practices**: Clean architecture, validation, error handling
5. **Be production-ready**: Full stack from database to UI

## Contributing

Contributions are welcome! This project demonstrates:
- Full-stack development with modern tools (FastAPI, Next.js)
- AI/LLM integration with proper validation
- Financial data processing and classification
- PDF/CSV parsing with real-world edge cases
- Database design for financial applications

Feel free to:
- Report issues or bugs
- Suggest new features
- Submit pull requests
- Fork for your own use

## License

MIT License - Feel free to use, modify, and distribute for personal or commercial use.

## Acknowledgments

- **Anthropic Claude** for intelligent transaction classification
- **FastAPI** for the excellent Python framework
- **Next.js** for the React framework and developer experience
- **pdfplumber** for PDF text extraction
- **Tailwind CSS** for rapid UI development
