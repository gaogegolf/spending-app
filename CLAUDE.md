# Project Guidelines

## Database

- **SQLite database**: `backend/spending_app.db`
- **Always back up before destructive operations** (data cleanup, migrations, bulk deletes):
  ```bash
  cp backend/spending_app.db backend/spending_app.db.backup-$(date +%Y%m%d)
  ```
- To restore: `cp backend/spending_app.db.backup-YYYYMMDD backend/spending_app.db`

## Stack

- **Backend**: FastAPI + SQLAlchemy + SQLite (`backend/`)
- **Frontend**: Next.js (App Router) + TypeScript + Tailwind CSS (`frontend/`)
- **Python venv**: `backend/venv/bin/python` (no global pytest installed)

## Running Services

```bash
# Backend
cd backend && ./venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev -- -p 3001
```
