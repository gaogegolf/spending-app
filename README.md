# Personal Finance Manager

[![English](https://img.shields.io/badge/lang-English-blue)](README.md)
[![中文](https://img.shields.io/badge/lang-中文-red)](README.zh-CN.md)

A full-stack personal finance app that imports bank/credit card statements, classifies transactions with AI, and tracks spending and net worth.

**Tech Stack**: FastAPI + Next.js + SQLAlchemy + Claude AI

## Features

### Statement Import
- **Multi-Format**: CSV and PDF support
- **Supported Banks**: Chase, Fidelity, Amex, Capital One, Wells Fargo, Ally, Wealthfront, IBKR, Vanguard 401(k)
- **Unknown Format Handling**: AI-powered extraction for unsupported PDF formats using Claude Vision
- **Smart Detection**: Auto-detects columns in CSV files
- **AI Classification**: Claude AI categorizes transactions automatically
- **Deduplication**: Hash-based prevention of duplicate imports

### Net Worth Tracking
- **Bank Balances**: Track checking/savings account balances
- **Brokerage Accounts**: Import investment statements
- **401(k) Support**: Vanguard statement parsing
- **Multi-Currency**: Support for multiple currencies

### Analytics Dashboard
- **Monthly Stats**: Spending, income, and net totals
- **Category Breakdown**: Visual spending distribution
- **Date Range Filter**: Custom period analysis
- **Bar Chart Toggle**: Visualize trends
- **Transaction Grouping**: Group similar transactions

### Transaction Management
- **Smart Filters**: By account, type, category, date
- **Notes**: Add notes to transactions
- **Review Queue**: Flag items needing attention
- **Bulk Operations**: Manage multiple transactions

### Merchant Categories
- **Custom Mappings**: Save merchant-to-category mappings
- **Auto-Apply**: Automatically categorize future transactions
- **Bulk Management**: View and edit all merchant mappings

### Rules Engine
- **Text Match**: Categorize by description keywords
- **Regex Support**: Advanced pattern matching
- **Amount Range**: Rules based on transaction amounts
- **Priority Order**: Control rule execution order

### Reports & Export
- **Year-over-Year**: Compare spending across years
- **Monthly Comparison**: Same month, different years
- **Spending Velocity**: Track spending pace within month
- **CSV Export**: Download transactions for external use

### Authentication & Account Management
- **User Registration**: With password strength indicator
- **Session Management**: View and revoke active login sessions
- **Profile Settings**: Update email and username
- **Change Password**: With real-time strength validation
- **Delete Account**: Permanently remove account and all data
- **Multi-Device**: Track logins across devices

## Business Logic

| Type | is_spend | is_income |
|------|----------|-----------|
| EXPENSE | true | false |
| INCOME | false | true |
| PAYMENT | false | false |
| TRANSFER | false | false |
| REFUND | false | false |
| FEE_INTEREST | true | false |

**Total Spending** = SUM(transactions WHERE is_spend=true)

## Quick Start

### Prerequisites
- Python 3.9+
- Node.js 18+
- [Anthropic API Key](https://console.anthropic.com/)

### Backend
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add ANTHROPIC_API_KEY
alembic upgrade head
uvicorn app.main:app --reload
```
Backend: http://localhost:8000

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Frontend: http://localhost:3001

### Troubleshooting

**Virtual environment not working (bad interpreter error)**

If you cloned the repo and the venv was created on a different machine, you'll see an error like:
```
bad interpreter: /old/path/to/python: no such file or directory
```
Fix by recreating the virtual environment:
```bash
cd backend
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**npm install fails with E401/authentication error**

If npm install fails with password or authentication errors, try specifying the public registry:
```bash
npm install --registry https://registry.npmjs.org/
```

**Running services with absolute paths**

If you prefer to run the services without activating the virtual environment:
```bash
# Backend (from project root)
./backend/venv/bin/uvicorn app.main:app --reload --app-dir ./backend

# Frontend (from frontend directory)
./node_modules/.bin/next dev -p 3001
```

**Missing email-validator or bcrypt errors**

If you see errors about missing `email-validator` or bcrypt version issues:
```bash
pip install email-validator 'bcrypt<4.1'
```

**Default login credentials**

After running migrations, a default user is created:
- Email: `default@example.com`
- Password: `changeme123`

You should change the password or create a new account after first login.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/auth/register` | Register new user |
| `POST /api/v1/auth/login` | Login and get tokens |
| `GET /api/v1/auth/sessions` | List active sessions |
| `PATCH /api/v1/auth/profile` | Update profile |
| `DELETE /api/v1/auth/account` | Delete account |
| `POST /api/v1/imports/upload` | Upload statement file |
| `GET /api/v1/transactions` | List transactions (with filters) |
| `GET /api/v1/stats/monthly` | Monthly summary |
| `GET /api/v1/stats/yoy` | Year-over-year comparison |
| `GET /api/v1/accounts` | List accounts |
| `GET /api/v1/merchant-categories` | List merchant mappings |
| `GET /api/v1/rules` | List categorization rules |
| `GET /api/v1/reports/export` | Export transactions to CSV |

Full API docs: http://localhost:8000/docs

## Supported Statement Formats

| Bank | Format | Status |
|------|--------|--------|
| Chase Credit Card | PDF | Supported |
| Chase Checking/Savings | PDF | Supported |
| Fidelity Visa | PDF | Supported |
| Fidelity Brokerage | PDF | Supported |
| American Express | PDF | Supported |
| Capital One | PDF | Supported |
| Wells Fargo | PDF | Supported |
| Ally Bank | PDF | Supported |
| IBKR | PDF | Supported |
| Vanguard 401(k) | PDF | Supported |
| Wealthfront | PDF | Supported |
| Any Bank | CSV | Supported |
| Unknown Banks | PDF | AI Fallback* |

*Unknown PDF formats use Claude Vision for extraction when pattern matching fails. Set `ENABLE_LLM_PDF_EXTRACTION=false` to disable.

## Privacy & Security
- **Data Isolation**: Multi-user support with strict data separation
- **JWT Authentication**: Secure token-based auth with refresh tokens
- **Minimal AI Data**: Only date/description/amount sent to AI (no personal info)
- **Local Storage**: SQLite database by default
- **Auto Cleanup**: Uploaded files deleted after processing

## License
MIT
