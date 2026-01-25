# Personal Finance Manager

[![English](https://img.shields.io/badge/lang-English-blue)](README.md)
[![中文](https://img.shields.io/badge/lang-中文-red)](README.zh-CN.md)

A full-stack personal finance app that imports bank/credit card statements, classifies transactions with AI, and tracks spending and net worth.

**Tech Stack**: FastAPI + Next.js + SQLAlchemy + Claude AI

## Features

### Statement Import
- **Multi-Format**: CSV and PDF support
- **Supported Banks**: Chase, Fidelity, Amex, Capital One, Wells Fargo, Ally, IBKR, Vanguard 401(k)
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
python -m venv venv && source venv/bin/activate
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
| `GET /api/v1/accounts` | List accounts |

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
| Any Bank | CSV | Supported |

## Privacy & Security
- Only date/description/amount sent to AI (no personal info)
- Local SQLite database by default
- Uploaded files deleted after processing

## License
MIT
