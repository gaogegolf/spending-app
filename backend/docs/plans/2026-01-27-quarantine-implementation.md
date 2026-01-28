# Quarantine Transactions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a quarantine system that imports valid transactions while capturing failures for in-app review and retry.

**Architecture:** Failed transactions are stored in a separate `quarantined_transactions` table with raw data and error details. A new service handles retry logic, and API endpoints enable viewing, editing, and retrying quarantined rows. The import service is modified to quarantine failures instead of silently skipping them.

**Tech Stack:** Python/FastAPI backend, SQLAlchemy ORM, Alembic migrations, Pydantic schemas, React/Next.js frontend

---

## Task 1: Create Quarantined Transaction Model

**Files:**
- Create: `backend/app/models/quarantined_transaction.py`
- Modify: `backend/app/models/__init__.py`

**Step 1: Create the model file**

Create `backend/app/models/quarantined_transaction.py`:

```python
"""Quarantined transaction model - stores failed import rows for review."""

from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.database import Base


class QuarantineErrorType(str, enum.Enum):
    """Types of quarantine errors."""

    PARSE_ERROR = "PARSE_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DUPLICATE = "DUPLICATE"


class QuarantineStatus(str, enum.Enum):
    """Quarantine item status."""

    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    DISCARDED = "DISCARDED"


class QuarantinedTransaction(Base):
    """Quarantined transaction model for failed import rows."""

    __tablename__ = "quarantined_transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    import_id = Column(String(36), ForeignKey("import_records.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(String(36), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Original data
    raw_data = Column(JSON, nullable=False)  # Original row as parsed

    # Error details
    error_type = Column(Enum(QuarantineErrorType), nullable=False)
    error_message = Column(Text, nullable=False)
    error_field = Column(String(100), nullable=True)  # Which field caused the issue

    # Status tracking
    retry_count = Column(Integer, default=0)
    status = Column(Enum(QuarantineStatus), default=QuarantineStatus.PENDING, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    # Relationships
    import_record = relationship("ImportRecord", back_populates="quarantined_transactions")
    account = relationship("Account")
    user = relationship("User")

    def __repr__(self):
        return f"<QuarantinedTransaction(id={self.id}, error_type={self.error_type}, status={self.status})>"
```

**Step 2: Update models __init__.py**

Add to `backend/app/models/__init__.py`:

```python
from app.models.quarantined_transaction import (
    QuarantinedTransaction,
    QuarantineErrorType,
    QuarantineStatus,
)
```

**Step 3: Add relationship to ImportRecord**

Modify `backend/app/models/import_record.py`, add after line 53:

```python
    quarantined_transactions = relationship("QuarantinedTransaction", back_populates="import_record", cascade="all, delete-orphan")
```

**Step 4: Verify model imports correctly**

Run: `cd backend && ./venv/bin/python -c "from app.models.quarantined_transaction import QuarantinedTransaction; print('Model OK')"`

Expected: `Model OK`

**Step 5: Commit**

```bash
git add backend/app/models/quarantined_transaction.py backend/app/models/__init__.py backend/app/models/import_record.py
git commit -m "feat: add QuarantinedTransaction model"
```

---

## Task 2: Create Alembic Migration

**Files:**
- Create: `backend/alembic/versions/b1c2d3e4f5a6_add_quarantine_tables.py`

**Step 1: Create migration file**

Create `backend/alembic/versions/b1c2d3e4f5a6_add_quarantine_tables.py`:

```python
"""Add quarantine tables.

Adds quarantined_transactions table and quarantine columns to import_records.

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-01-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = 'a0b1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add quarantined_transactions table and update import_records."""

    # Create quarantined_transactions table
    op.execute("""
        CREATE TABLE quarantined_transactions (
            id VARCHAR(36) PRIMARY KEY,
            import_id VARCHAR(36) NOT NULL REFERENCES import_records(id) ON DELETE CASCADE,
            account_id VARCHAR(36) REFERENCES accounts(id) ON DELETE SET NULL,
            user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            raw_data JSON NOT NULL,
            error_type VARCHAR(20) NOT NULL,
            error_message TEXT NOT NULL,
            error_field VARCHAR(100),
            retry_count INTEGER DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME
        )
    """)

    # Create index on import_id for faster lookups
    op.execute("CREATE INDEX ix_quarantined_transactions_import_id ON quarantined_transactions(import_id)")

    # Create index on status for filtering pending items
    op.execute("CREATE INDEX ix_quarantined_transactions_status ON quarantined_transactions(status)")

    # Create index on user_id for user-specific queries
    op.execute("CREATE INDEX ix_quarantined_transactions_user_id ON quarantined_transactions(user_id)")

    # Add columns to import_records (SQLite requires table recreation)
    op.execute("""
        CREATE TABLE import_records_new (
            id VARCHAR(36) PRIMARY KEY,
            account_id VARCHAR(36) REFERENCES accounts(id) ON DELETE CASCADE,
            user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
            source_type VARCHAR(10) NOT NULL,
            filename VARCHAR(500) NOT NULL,
            file_size_bytes INTEGER,
            file_hash VARCHAR(64),
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            error_message TEXT,
            transactions_imported INTEGER DEFAULT 0,
            transactions_duplicate INTEGER DEFAULT 0,
            transactions_quarantined INTEGER DEFAULT 0,
            quarantine_resolved BOOLEAN DEFAULT 1,
            import_metadata JSON,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME
        )
    """)

    # Copy existing data
    op.execute("""
        INSERT INTO import_records_new (
            id, account_id, user_id, source_type, filename, file_size_bytes, file_hash,
            status, error_message, transactions_imported, transactions_duplicate,
            transactions_quarantined, quarantine_resolved, import_metadata, created_at, completed_at
        )
        SELECT
            id, account_id, user_id, source_type, filename, file_size_bytes, file_hash,
            status, error_message, transactions_imported, transactions_duplicate,
            0, 1, import_metadata, created_at, completed_at
        FROM import_records
    """)

    # Drop old table and rename new
    op.execute("DROP TABLE import_records")
    op.execute("ALTER TABLE import_records_new RENAME TO import_records")

    # Recreate indexes on import_records
    op.execute("CREATE INDEX ix_import_records_account_id ON import_records(account_id)")
    op.execute("CREATE INDEX ix_import_records_user_id ON import_records(user_id)")


def downgrade() -> None:
    """Remove quarantine tables and columns."""

    # Drop quarantined_transactions table
    op.execute("DROP TABLE IF EXISTS quarantined_transactions")

    # Remove quarantine columns from import_records (recreate without them)
    op.execute("""
        CREATE TABLE import_records_new (
            id VARCHAR(36) PRIMARY KEY,
            account_id VARCHAR(36) REFERENCES accounts(id) ON DELETE CASCADE,
            user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
            source_type VARCHAR(10) NOT NULL,
            filename VARCHAR(500) NOT NULL,
            file_size_bytes INTEGER,
            file_hash VARCHAR(64),
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            error_message TEXT,
            transactions_imported INTEGER DEFAULT 0,
            transactions_duplicate INTEGER DEFAULT 0,
            import_metadata JSON,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME
        )
    """)

    op.execute("""
        INSERT INTO import_records_new
        SELECT id, account_id, user_id, source_type, filename, file_size_bytes, file_hash,
               status, error_message, transactions_imported, transactions_duplicate,
               import_metadata, created_at, completed_at
        FROM import_records
    """)

    op.execute("DROP TABLE import_records")
    op.execute("ALTER TABLE import_records_new RENAME TO import_records")
```

**Step 2: Update ImportRecord model with new columns**

Add to `backend/app/models/import_record.py` after line 44 (`transactions_duplicate`):

```python
    transactions_quarantined = Column(Integer, default=0)
    quarantine_resolved = Column(Boolean, default=True)
```

Also add `Boolean` to the imports at the top:

```python
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Enum, JSON, Boolean
```

**Step 3: Run migration**

Run: `cd backend && ./venv/bin/alembic upgrade head`

Expected: Migration completes without errors

**Step 4: Verify table exists**

Run: `cd backend && ./venv/bin/python -c "from app.database import SessionLocal; db = SessionLocal(); print(db.execute('SELECT COUNT(*) FROM quarantined_transactions').fetchone())"`

Expected: `(0,)`

**Step 5: Commit**

```bash
git add backend/alembic/versions/b1c2d3e4f5a6_add_quarantine_tables.py backend/app/models/import_record.py
git commit -m "feat: add quarantine migration and ImportRecord columns"
```

---

## Task 3: Create Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/quarantine.py`

**Step 1: Create schemas file**

Create `backend/app/schemas/quarantine.py`:

```python
"""Pydantic schemas for Quarantine API."""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any, List

from app.models.quarantined_transaction import QuarantineErrorType, QuarantineStatus


class QuarantinedTransactionResponse(BaseModel):
    """Schema for quarantined transaction response."""

    id: str
    import_id: str
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    user_id: str
    raw_data: Dict[str, Any]
    error_type: QuarantineErrorType
    error_message: str
    error_field: Optional[str] = None
    retry_count: int
    status: QuarantineStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None

    # Convenience fields for display
    import_filename: Optional[str] = None

    class Config:
        from_attributes = True


class QuarantineListResponse(BaseModel):
    """Schema for list of quarantined transactions."""

    items: List[QuarantinedTransactionResponse]
    total: int
    pending_count: int


class QuarantineUpdateRequest(BaseModel):
    """Schema for updating quarantined transaction fields."""

    date: Optional[str] = None
    amount: Optional[float] = None
    description: Optional[str] = None
    merchant_normalized: Optional[str] = None
    account_id: Optional[str] = None


class QuarantineRetryResponse(BaseModel):
    """Schema for retry response."""

    id: str
    status: QuarantineStatus
    error_message: Optional[str] = None
    transaction_id: Optional[str] = None  # If successfully imported


class QuarantineBulkRequest(BaseModel):
    """Schema for bulk operations."""

    ids: List[str] = Field(..., min_length=1)


class QuarantineBulkResponse(BaseModel):
    """Schema for bulk operation response."""

    success_count: int
    failure_count: int
    results: List[QuarantineRetryResponse]
```

**Step 2: Verify schemas import correctly**

Run: `cd backend && ./venv/bin/python -c "from app.schemas.quarantine import QuarantinedTransactionResponse; print('Schemas OK')"`

Expected: `Schemas OK`

**Step 3: Commit**

```bash
git add backend/app/schemas/quarantine.py
git commit -m "feat: add quarantine Pydantic schemas"
```

---

## Task 4: Create Quarantine Service

**Files:**
- Create: `backend/app/services/quarantine_service.py`

**Step 1: Create the service file**

Create `backend/app/services/quarantine_service.py`:

```python
"""Quarantine service - business logic for managing quarantined transactions."""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.models.quarantined_transaction import (
    QuarantinedTransaction,
    QuarantineErrorType,
    QuarantineStatus,
)
from app.models.import_record import ImportRecord
from app.models.transaction import Transaction
from app.models.account import Account
from app.services.deduplication import DeduplicationService

logger = logging.getLogger(__name__)


class QuarantineService:
    """Service for managing quarantined transactions."""

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id
        self.dedup_service = DeduplicationService(db)

    def list_quarantined(
        self,
        import_id: Optional[str] = None,
        status: Optional[QuarantineStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[QuarantinedTransaction], int, int]:
        """List quarantined transactions for current user.

        Args:
            import_id: Filter by specific import
            status: Filter by status
            limit: Max items to return
            offset: Pagination offset

        Returns:
            Tuple of (items, total_count, pending_count)
        """
        query = self.db.query(QuarantinedTransaction).filter(
            QuarantinedTransaction.user_id == self.user_id
        )

        if import_id:
            query = query.filter(QuarantinedTransaction.import_id == import_id)

        if status:
            query = query.filter(QuarantinedTransaction.status == status)

        total = query.count()

        # Get pending count (for badge display)
        pending_count = self.db.query(QuarantinedTransaction).filter(
            QuarantinedTransaction.user_id == self.user_id,
            QuarantinedTransaction.status == QuarantineStatus.PENDING,
        ).count()

        items = query.order_by(QuarantinedTransaction.created_at.desc()).offset(offset).limit(limit).all()

        return items, total, pending_count

    def get_quarantined(self, quarantine_id: str) -> Optional[QuarantinedTransaction]:
        """Get a single quarantined transaction."""
        return self.db.query(QuarantinedTransaction).filter(
            QuarantinedTransaction.id == quarantine_id,
            QuarantinedTransaction.user_id == self.user_id,
        ).first()

    def update_quarantined(
        self,
        quarantine_id: str,
        updates: Dict[str, Any],
    ) -> Optional[QuarantinedTransaction]:
        """Update fields on a quarantined transaction.

        Args:
            quarantine_id: ID of quarantined item
            updates: Dict of field updates (date, amount, description, etc.)

        Returns:
            Updated quarantined transaction or None if not found
        """
        item = self.get_quarantined(quarantine_id)
        if not item:
            return None

        if item.status != QuarantineStatus.PENDING:
            raise ValueError("Cannot update resolved or discarded item")

        # Update raw_data with new values
        raw_data = dict(item.raw_data)
        for key, value in updates.items():
            if value is not None:
                raw_data[key] = value

        item.raw_data = raw_data
        self.db.commit()
        self.db.refresh(item)

        return item

    def retry_quarantined(self, quarantine_id: str) -> Tuple[QuarantinedTransaction, Optional[str]]:
        """Attempt to retry importing a quarantined transaction.

        Args:
            quarantine_id: ID of quarantined item

        Returns:
            Tuple of (quarantined_item, transaction_id if success)
        """
        item = self.get_quarantined(quarantine_id)
        if not item:
            raise ValueError("Quarantined item not found")

        if item.status != QuarantineStatus.PENDING:
            raise ValueError("Cannot retry resolved or discarded item")

        # Validate and transform the raw data
        try:
            txn_data = self._validate_and_transform(item.raw_data, item.account_id)
        except ValueError as e:
            # Update error and increment retry count
            item.error_message = str(e)
            item.retry_count += 1
            self.db.commit()
            return item, None

        # Check for duplicates
        if item.account_id:
            import_record = item.import_record
            duplicate_hashes = self.dedup_service.check_duplicates(
                account_id=item.account_id,
                file_hash=import_record.file_hash if import_record else None,
                transactions=[txn_data],
            )
            if duplicate_hashes:
                item.error_type = QuarantineErrorType.DUPLICATE
                item.error_message = "Transaction is a duplicate of existing record"
                item.retry_count += 1
                self.db.commit()
                return item, None

        # Create the transaction
        transaction = self._create_transaction(txn_data, item)

        # Mark as resolved
        item.status = QuarantineStatus.RESOLVED
        item.resolved_at = datetime.utcnow()

        # Update import record counts
        if item.import_record:
            item.import_record.transactions_imported += 1
            item.import_record.transactions_quarantined -= 1
            # Check if all quarantine items are resolved
            pending = self.db.query(QuarantinedTransaction).filter(
                QuarantinedTransaction.import_id == item.import_id,
                QuarantinedTransaction.status == QuarantineStatus.PENDING,
            ).count()
            item.import_record.quarantine_resolved = (pending == 0)

        self.db.commit()

        return item, transaction.id

    def discard_quarantined(self, quarantine_id: str) -> Optional[QuarantinedTransaction]:
        """Discard a quarantined transaction (won't be imported).

        Args:
            quarantine_id: ID of quarantined item

        Returns:
            Updated quarantined transaction or None if not found
        """
        item = self.get_quarantined(quarantine_id)
        if not item:
            return None

        if item.status != QuarantineStatus.PENDING:
            raise ValueError("Cannot discard resolved or already discarded item")

        item.status = QuarantineStatus.DISCARDED
        item.resolved_at = datetime.utcnow()

        # Update import record
        if item.import_record:
            item.import_record.transactions_quarantined -= 1
            pending = self.db.query(QuarantinedTransaction).filter(
                QuarantinedTransaction.import_id == item.import_id,
                QuarantinedTransaction.status == QuarantineStatus.PENDING,
            ).count()
            item.import_record.quarantine_resolved = (pending == 0)

        self.db.commit()
        self.db.refresh(item)

        return item

    def bulk_retry(self, ids: List[str]) -> List[Tuple[str, bool, Optional[str], Optional[str]]]:
        """Retry multiple quarantined items.

        Args:
            ids: List of quarantine IDs to retry

        Returns:
            List of (id, success, transaction_id, error_message) tuples
        """
        results = []
        for qid in ids:
            try:
                item, txn_id = self.retry_quarantined(qid)
                success = item.status == QuarantineStatus.RESOLVED
                results.append((qid, success, txn_id, None if success else item.error_message))
            except ValueError as e:
                results.append((qid, False, None, str(e)))
        return results

    def bulk_discard(self, ids: List[str]) -> List[Tuple[str, bool, Optional[str]]]:
        """Discard multiple quarantined items.

        Args:
            ids: List of quarantine IDs to discard

        Returns:
            List of (id, success, error_message) tuples
        """
        results = []
        for qid in ids:
            try:
                item = self.discard_quarantined(qid)
                results.append((qid, item is not None, None))
            except ValueError as e:
                results.append((qid, False, str(e)))
        return results

    def _validate_and_transform(
        self,
        raw_data: Dict[str, Any],
        account_id: Optional[str],
    ) -> Dict[str, Any]:
        """Validate and transform raw data into transaction format.

        Args:
            raw_data: Raw row data from quarantine
            account_id: Target account ID

        Returns:
            Validated transaction data dict

        Raises:
            ValueError: If validation fails
        """
        errors = []

        # Validate date
        date_str = raw_data.get('date')
        if not date_str:
            errors.append("Missing date")
        else:
            try:
                # Try common formats
                from datetime import datetime
                parsed_date = None
                for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%d/%m/%Y']:
                    try:
                        parsed_date = datetime.strptime(str(date_str), fmt).date()
                        break
                    except ValueError:
                        continue
                if not parsed_date:
                    errors.append(f"Cannot parse date: {date_str}")
            except Exception as e:
                errors.append(f"Invalid date: {e}")

        # Validate amount
        amount = raw_data.get('amount')
        if amount is None:
            errors.append("Missing amount")
        else:
            try:
                amount_decimal = Decimal(str(amount))
            except (InvalidOperation, ValueError):
                errors.append(f"Invalid amount: {amount}")

        # Validate description
        description = raw_data.get('description_raw') or raw_data.get('description')
        if not description:
            errors.append("Missing description")

        if errors:
            raise ValueError("; ".join(errors))

        # Return transformed data
        return {
            **raw_data,
            'date': str(parsed_date) if parsed_date else date_str,
            'amount': float(amount_decimal) if 'amount_decimal' in dir() else float(amount),
        }

    def _create_transaction(
        self,
        txn_data: Dict[str, Any],
        quarantine_item: QuarantinedTransaction,
    ) -> Transaction:
        """Create a transaction from validated data.

        Args:
            txn_data: Validated transaction data
            quarantine_item: Source quarantine item

        Returns:
            Created Transaction
        """
        from app.models.transaction import Transaction, TransactionType

        # Determine transaction type
        amount = float(txn_data.get('amount', 0))
        txn_type = TransactionType.EXPENSE if amount > 0 else TransactionType.INCOME

        transaction = Transaction(
            account_id=quarantine_item.account_id,
            import_id=quarantine_item.import_id,
            date=txn_data.get('date'),
            amount=abs(amount),
            description_raw=txn_data.get('description_raw', txn_data.get('description', '')),
            merchant_normalized=txn_data.get('merchant_normalized', ''),
            transaction_type=txn_type,
            category=txn_data.get('category', 'Uncategorized'),
            is_spend=amount > 0,
            is_income=amount < 0,
            needs_review=True,
        )

        self.db.add(transaction)
        return transaction


def create_quarantine_item(
    db: Session,
    import_record: ImportRecord,
    raw_data: Dict[str, Any],
    error_type: QuarantineErrorType,
    error_message: str,
    error_field: Optional[str] = None,
) -> QuarantinedTransaction:
    """Helper to create a quarantine item during import.

    Args:
        db: Database session
        import_record: Parent import record
        raw_data: Original row data
        error_type: Type of error
        error_message: Human-readable error
        error_field: Field that caused the error

    Returns:
        Created QuarantinedTransaction
    """
    item = QuarantinedTransaction(
        import_id=import_record.id,
        account_id=import_record.account_id,
        user_id=import_record.user_id or (import_record.account.user_id if import_record.account else None),
        raw_data=raw_data,
        error_type=error_type,
        error_message=error_message,
        error_field=error_field,
    )
    db.add(item)
    return item
```

**Step 2: Verify service imports correctly**

Run: `cd backend && ./venv/bin/python -c "from app.services.quarantine_service import QuarantineService; print('Service OK')"`

Expected: `Service OK`

**Step 3: Commit**

```bash
git add backend/app/services/quarantine_service.py
git commit -m "feat: add QuarantineService with retry logic"
```

---

## Task 5: Create API Routes

**Files:**
- Create: `backend/app/api/v1/quarantine.py`
- Modify: `backend/app/main.py`

**Step 1: Create the API routes file**

Create `backend/app/api/v1/quarantine.py`:

```python
"""Quarantine API endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.quarantine_service import QuarantineService
from app.schemas.quarantine import (
    QuarantinedTransactionResponse,
    QuarantineListResponse,
    QuarantineUpdateRequest,
    QuarantineRetryResponse,
    QuarantineBulkRequest,
    QuarantineBulkResponse,
)
from app.models.quarantined_transaction import QuarantineStatus
from app.models.user import User
from app.middleware.auth import get_current_active_user

router = APIRouter()


def _to_response(item, db) -> QuarantinedTransactionResponse:
    """Convert model to response schema with related data."""
    return QuarantinedTransactionResponse(
        id=item.id,
        import_id=item.import_id,
        account_id=item.account_id,
        account_name=item.account.name if item.account else None,
        user_id=item.user_id,
        raw_data=item.raw_data,
        error_type=item.error_type,
        error_message=item.error_message,
        error_field=item.error_field,
        retry_count=item.retry_count,
        status=item.status,
        created_at=item.created_at,
        resolved_at=item.resolved_at,
        import_filename=item.import_record.filename if item.import_record else None,
    )


@router.get("/quarantine", response_model=QuarantineListResponse)
async def list_quarantined(
    import_id: Optional[str] = Query(None, description="Filter by import ID"),
    status: Optional[QuarantineStatus] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List quarantined transactions for current user."""
    service = QuarantineService(db, current_user.id)
    items, total, pending_count = service.list_quarantined(
        import_id=import_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    return QuarantineListResponse(
        items=[_to_response(item, db) for item in items],
        total=total,
        pending_count=pending_count,
    )


@router.get("/quarantine/{quarantine_id}", response_model=QuarantinedTransactionResponse)
async def get_quarantined(
    quarantine_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get a single quarantined transaction."""
    service = QuarantineService(db, current_user.id)
    item = service.get_quarantined(quarantine_id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quarantined transaction not found",
        )

    return _to_response(item, db)


@router.patch("/quarantine/{quarantine_id}", response_model=QuarantinedTransactionResponse)
async def update_quarantined(
    quarantine_id: str,
    updates: QuarantineUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update fields on a quarantined transaction."""
    service = QuarantineService(db, current_user.id)

    try:
        item = service.update_quarantined(
            quarantine_id,
            updates.model_dump(exclude_none=True),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quarantined transaction not found",
        )

    return _to_response(item, db)


@router.post("/quarantine/{quarantine_id}/retry", response_model=QuarantineRetryResponse)
async def retry_quarantined(
    quarantine_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Retry importing a quarantined transaction."""
    service = QuarantineService(db, current_user.id)

    try:
        item, txn_id = service.retry_quarantined(quarantine_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return QuarantineRetryResponse(
        id=item.id,
        status=item.status,
        error_message=item.error_message if item.status == QuarantineStatus.PENDING else None,
        transaction_id=txn_id,
    )


@router.post("/quarantine/{quarantine_id}/discard", response_model=QuarantinedTransactionResponse)
async def discard_quarantined(
    quarantine_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Discard a quarantined transaction."""
    service = QuarantineService(db, current_user.id)

    try:
        item = service.discard_quarantined(quarantine_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quarantined transaction not found",
        )

    return _to_response(item, db)


@router.post("/quarantine/bulk-retry", response_model=QuarantineBulkResponse)
async def bulk_retry(
    request: QuarantineBulkRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Retry multiple quarantined transactions."""
    service = QuarantineService(db, current_user.id)
    results = service.bulk_retry(request.ids)

    return QuarantineBulkResponse(
        success_count=sum(1 for _, success, _, _ in results if success),
        failure_count=sum(1 for _, success, _, _ in results if not success),
        results=[
            QuarantineRetryResponse(
                id=qid,
                status=QuarantineStatus.RESOLVED if success else QuarantineStatus.PENDING,
                error_message=error,
                transaction_id=txn_id,
            )
            for qid, success, txn_id, error in results
        ],
    )


@router.post("/quarantine/bulk-discard", response_model=QuarantineBulkResponse)
async def bulk_discard(
    request: QuarantineBulkRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Discard multiple quarantined transactions."""
    service = QuarantineService(db, current_user.id)
    results = service.bulk_discard(request.ids)

    return QuarantineBulkResponse(
        success_count=sum(1 for _, success, _ in results if success),
        failure_count=sum(1 for _, success, _ in results if not success),
        results=[
            QuarantineRetryResponse(
                id=qid,
                status=QuarantineStatus.DISCARDED if success else QuarantineStatus.PENDING,
                error_message=error,
                transaction_id=None,
            )
            for qid, success, error in results
        ],
    )
```

**Step 2: Register router in main.py**

Add to `backend/app/main.py` imports (line 89):

```python
from app.api.v1 import accounts, imports, transactions, stats, merchant_categories, rules, brokerage, reports, auth, backup, quarantine
```

Add router registration after line 100:

```python
app.include_router(quarantine.router, prefix="/api/v1", tags=["quarantine"])
```

**Step 3: Verify API starts correctly**

Run: `cd backend && ./venv/bin/python -c "from app.main import app; print('API OK')"`

Expected: `API OK`

**Step 4: Commit**

```bash
git add backend/app/api/v1/quarantine.py backend/app/main.py
git commit -m "feat: add quarantine API endpoints"
```

---

## Task 6: Modify Import Service to Quarantine Failures

**Files:**
- Modify: `backend/app/services/import_service.py`

**Step 1: Add quarantine imports**

Add to imports at top of `backend/app/services/import_service.py`:

```python
from app.models.quarantined_transaction import QuarantineErrorType
from app.services.quarantine_service import create_quarantine_item
```

**Step 2: Create helper method for transaction validation**

Add this method to the `ImportService` class (around line 550, before `_get_file_path`):

```python
    def _validate_transaction_data(self, txn_data: dict, row_index: int) -> tuple[bool, str, str]:
        """Validate a single transaction's data.

        Args:
            txn_data: Transaction data dict
            row_index: Row number for error reporting

        Returns:
            Tuple of (is_valid, error_message, error_field)
        """
        # Check required fields
        if not txn_data.get('date'):
            return False, f"Row {row_index}: Missing date", "date"

        if txn_data.get('amount') is None:
            return False, f"Row {row_index}: Missing amount", "amount"

        # Validate date format
        date_val = txn_data.get('date')
        if date_val:
            try:
                from datetime import datetime, date
                if isinstance(date_val, str):
                    # Try to parse common formats
                    parsed = None
                    for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%d/%m/%Y']:
                        try:
                            parsed = datetime.strptime(date_val, fmt)
                            break
                        except ValueError:
                            continue
                    if not parsed:
                        return False, f"Row {row_index}: Cannot parse date '{date_val}'", "date"
            except Exception as e:
                return False, f"Row {row_index}: Invalid date - {e}", "date"

        # Validate amount
        amount = txn_data.get('amount')
        if amount is not None:
            try:
                float(amount)
            except (ValueError, TypeError):
                return False, f"Row {row_index}: Invalid amount '{amount}'", "amount"

        return True, "", ""
```

**Step 3: Modify commit_import to quarantine failures**

In the `commit_import` method, find the loop that processes transactions (around line 330-400) and wrap individual transaction processing to catch errors.

Find this section (approximately line 455-530 where transactions are created) and modify to:

```python
            # Step 5: Create transaction objects
            success_count = 0
            quarantine_count = 0

            for i, txn_data in enumerate(all_classified_txns):
                # Validate before creating
                is_valid, error_msg, error_field = self._validate_transaction_data(txn_data, i + 1)

                if not is_valid:
                    # Quarantine invalid transaction
                    create_quarantine_item(
                        db=self.db,
                        import_record=import_record,
                        raw_data=txn_data,
                        error_type=QuarantineErrorType.PARSE_ERROR,
                        error_message=error_msg,
                        error_field=error_field,
                    )
                    quarantine_count += 1
                    continue

                try:
                    # Create transaction (existing code)
                    transaction = Transaction(
                        account_id=import_record.account_id,
                        import_id=import_record.id,
                        date=txn_data.get('date'),
                        amount=abs(float(txn_data.get('amount', 0))),
                        description_raw=txn_data.get('description_raw', ''),
                        merchant_normalized=txn_data.get('merchant_normalized', ''),
                        transaction_type=TransactionType(txn_data.get('transaction_type', 'EXPENSE')),
                        category=txn_data.get('category', 'Uncategorized'),
                        is_spend=txn_data.get('is_spend', True),
                        is_income=txn_data.get('is_income', False),
                        confidence=txn_data.get('confidence', 0.0),
                        classification_method=txn_data.get('classification_method', 'RULE'),
                        needs_review=txn_data.get('needs_review', False),
                        import_hash=txn_data.get('import_hash'),
                    )
                    self.db.add(transaction)
                    success_count += 1
                except Exception as e:
                    # Quarantine on any creation error
                    create_quarantine_item(
                        db=self.db,
                        import_record=import_record,
                        raw_data=txn_data,
                        error_type=QuarantineErrorType.VALIDATION_ERROR,
                        error_message=f"Failed to create transaction: {str(e)}",
                        error_field=None,
                    )
                    quarantine_count += 1
```

**Step 4: Update import record with quarantine count**

After the transaction loop, update the import record:

```python
            # Update import record with final counts
            import_record.transactions_imported = success_count
            import_record.transactions_duplicate = duplicate_count
            import_record.transactions_quarantined = quarantine_count
            import_record.quarantine_resolved = (quarantine_count == 0)

            if quarantine_count > 0 and success_count > 0:
                import_record.status = ImportStatus.PARTIAL
            elif success_count > 0:
                import_record.status = ImportStatus.SUCCESS
            else:
                import_record.status = ImportStatus.FAILED
```

**Step 5: Test import still works**

Run: `cd backend && ./venv/bin/python -c "from app.services.import_service import ImportService; print('Import service OK')"`

Expected: `Import service OK`

**Step 6: Commit**

```bash
git add backend/app/services/import_service.py
git commit -m "feat: modify import service to quarantine failed transactions"
```

---

## Task 7: Add Quarantine Count to Import Response

**Files:**
- Modify: `backend/app/schemas/import_record.py`
- Modify: `backend/app/api/v1/imports.py`

**Step 1: Update ImportStatusResponse schema**

Add to `ImportStatusResponse` in `backend/app/schemas/import_record.py`:

```python
    transactions_quarantined: int = 0
    quarantine_resolved: bool = True
```

**Step 2: Verify schema change**

Run: `cd backend && ./venv/bin/python -c "from app.schemas.import_record import ImportStatusResponse; print(ImportStatusResponse.model_fields.keys())"`

Expected: Should include `transactions_quarantined` and `quarantine_resolved`

**Step 3: Commit**

```bash
git add backend/app/schemas/import_record.py
git commit -m "feat: add quarantine fields to import response schema"
```

---

## Task 8: Create Frontend API Client

**Files:**
- Modify: `frontend/lib/api.ts`

**Step 1: Add quarantine types and API functions**

Add to `frontend/lib/api.ts`:

```typescript
// Quarantine types
export interface QuarantinedTransaction {
  id: string;
  import_id: string;
  account_id: string | null;
  account_name: string | null;
  user_id: string;
  raw_data: Record<string, any>;
  error_type: 'PARSE_ERROR' | 'VALIDATION_ERROR' | 'DUPLICATE';
  error_message: string;
  error_field: string | null;
  retry_count: number;
  status: 'PENDING' | 'RESOLVED' | 'DISCARDED';
  created_at: string;
  resolved_at: string | null;
  import_filename: string | null;
}

export interface QuarantineListResponse {
  items: QuarantinedTransaction[];
  total: number;
  pending_count: number;
}

export interface QuarantineRetryResponse {
  id: string;
  status: 'PENDING' | 'RESOLVED' | 'DISCARDED';
  error_message: string | null;
  transaction_id: string | null;
}

// Quarantine API functions
export async function getQuarantinedTransactions(params?: {
  import_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<QuarantineListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.import_id) searchParams.set('import_id', params.import_id);
  if (params?.status) searchParams.set('status', params.status);
  if (params?.limit) searchParams.set('limit', params.limit.toString());
  if (params?.offset) searchParams.set('offset', params.offset.toString());

  const url = `/api/v1/quarantine${searchParams.toString() ? '?' + searchParams.toString() : ''}`;
  return fetchApi(url);
}

export async function getQuarantinedTransaction(id: string): Promise<QuarantinedTransaction> {
  return fetchApi(`/api/v1/quarantine/${id}`);
}

export async function updateQuarantinedTransaction(
  id: string,
  updates: Partial<{ date: string; amount: number; description: string; account_id: string }>
): Promise<QuarantinedTransaction> {
  return fetchApi(`/api/v1/quarantine/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}

export async function retryQuarantinedTransaction(id: string): Promise<QuarantineRetryResponse> {
  return fetchApi(`/api/v1/quarantine/${id}/retry`, { method: 'POST' });
}

export async function discardQuarantinedTransaction(id: string): Promise<QuarantinedTransaction> {
  return fetchApi(`/api/v1/quarantine/${id}/discard`, { method: 'POST' });
}

export async function bulkRetryQuarantined(ids: string[]): Promise<{
  success_count: number;
  failure_count: number;
  results: QuarantineRetryResponse[];
}> {
  return fetchApi('/api/v1/quarantine/bulk-retry', {
    method: 'POST',
    body: JSON.stringify({ ids }),
  });
}

export async function bulkDiscardQuarantined(ids: string[]): Promise<{
  success_count: number;
  failure_count: number;
  results: QuarantineRetryResponse[];
}> {
  return fetchApi('/api/v1/quarantine/bulk-discard', {
    method: 'POST',
    body: JSON.stringify({ ids }),
  });
}
```

**Step 2: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat: add quarantine API client functions"
```

---

## Task 9: Create Quarantine Review Page

**Files:**
- Create: `frontend/app/quarantine/page.tsx`

**Step 1: Create the quarantine page**

Create `frontend/app/quarantine/page.tsx`:

```tsx
'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  getQuarantinedTransactions,
  updateQuarantinedTransaction,
  retryQuarantinedTransaction,
  discardQuarantinedTransaction,
  bulkRetryQuarantined,
  bulkDiscardQuarantined,
  QuarantinedTransaction,
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function QuarantinePage() {
  const [items, setItems] = useState<QuarantinedTransaction[]>([]);
  const [total, setTotal] = useState(0);
  const [pendingCount, setPendingCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<Record<string, any>>({});
  const [statusFilter, setStatusFilter] = useState<string>('PENDING');

  useEffect(() => {
    loadQuarantined();
  }, [statusFilter]);

  async function loadQuarantined() {
    try {
      setLoading(true);
      const data = await getQuarantinedTransactions({
        status: statusFilter || undefined,
        limit: 100,
      });
      setItems(data.items);
      setTotal(data.total);
      setPendingCount(data.pending_count);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load quarantined transactions');
    } finally {
      setLoading(false);
    }
  }

  async function handleRetry(id: string) {
    try {
      const result = await retryQuarantinedTransaction(id);
      if (result.status === 'RESOLVED') {
        // Remove from list or refresh
        loadQuarantined();
      } else {
        // Update error message in UI
        setItems(items.map(item =>
          item.id === id ? { ...item, error_message: result.error_message || item.error_message, retry_count: item.retry_count + 1 } : item
        ));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Retry failed');
    }
  }

  async function handleDiscard(id: string) {
    try {
      await discardQuarantinedTransaction(id);
      loadQuarantined();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Discard failed');
    }
  }

  async function handleBulkRetry() {
    if (selectedIds.size === 0) return;
    try {
      await bulkRetryQuarantined(Array.from(selectedIds));
      setSelectedIds(new Set());
      loadQuarantined();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Bulk retry failed');
    }
  }

  async function handleBulkDiscard() {
    if (selectedIds.size === 0) return;
    try {
      await bulkDiscardQuarantined(Array.from(selectedIds));
      setSelectedIds(new Set());
      loadQuarantined();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Bulk discard failed');
    }
  }

  function startEdit(item: QuarantinedTransaction) {
    setEditingId(item.id);
    setEditValues({
      date: item.raw_data.date || '',
      amount: item.raw_data.amount || '',
      description: item.raw_data.description_raw || item.raw_data.description || '',
    });
  }

  async function saveEdit(id: string) {
    try {
      await updateQuarantinedTransaction(id, editValues);
      setEditingId(null);
      loadQuarantined();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed');
    }
  }

  function toggleSelect(id: string) {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedIds(newSelected);
  }

  function toggleSelectAll() {
    if (selectedIds.size === items.filter(i => i.status === 'PENDING').length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(items.filter(i => i.status === 'PENDING').map(i => i.id)));
    }
  }

  const pendingItems = items.filter(i => i.status === 'PENDING');

  return (
    <div className="container mx-auto py-8 px-4">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">Quarantined Transactions</h1>
          <p className="text-gray-600">
            {pendingCount} pending review
          </p>
        </div>
        <Link href="/imports">
          <Button variant="outline">Back to Imports</Button>
        </Link>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
          <p className="text-red-800">{error}</p>
          <button onClick={() => setError(null)} className="text-red-600 underline text-sm">
            Dismiss
          </button>
        </div>
      )}

      {/* Filters and Bulk Actions */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="flex flex-wrap gap-4 items-center justify-between">
            <div className="flex gap-2">
              <Button
                variant={statusFilter === 'PENDING' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStatusFilter('PENDING')}
              >
                Pending ({pendingCount})
              </Button>
              <Button
                variant={statusFilter === '' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStatusFilter('')}
              >
                All ({total})
              </Button>
            </div>

            {selectedIds.size > 0 && (
              <div className="flex gap-2">
                <Button size="sm" onClick={handleBulkRetry}>
                  Retry Selected ({selectedIds.size})
                </Button>
                <Button size="sm" variant="destructive" onClick={handleBulkDiscard}>
                  Discard Selected
                </Button>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Items List */}
      {loading ? (
        <div className="text-center py-8">Loading...</div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-gray-500">
            No quarantined transactions found.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {pendingItems.length > 0 && statusFilter === 'PENDING' && (
            <div className="flex items-center gap-2 mb-2">
              <input
                type="checkbox"
                checked={selectedIds.size === pendingItems.length}
                onChange={toggleSelectAll}
                className="rounded"
              />
              <span className="text-sm text-gray-600">Select all</span>
            </div>
          )}

          {items.map((item) => (
            <Card key={item.id} className={item.status !== 'PENDING' ? 'opacity-60' : ''}>
              <CardContent className="pt-6">
                <div className="flex items-start gap-4">
                  {item.status === 'PENDING' && (
                    <input
                      type="checkbox"
                      checked={selectedIds.has(item.id)}
                      onChange={() => toggleSelect(item.id)}
                      className="mt-1 rounded"
                    />
                  )}

                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <Badge variant={
                        item.status === 'PENDING' ? 'destructive' :
                        item.status === 'RESOLVED' ? 'default' : 'secondary'
                      }>
                        {item.status}
                      </Badge>
                      <Badge variant="outline">{item.error_type}</Badge>
                      {item.error_field && (
                        <Badge variant="outline">Field: {item.error_field}</Badge>
                      )}
                      {item.retry_count > 0 && (
                        <span className="text-sm text-gray-500">
                          ({item.retry_count} retries)
                        </span>
                      )}
                    </div>

                    <p className="text-red-600 text-sm mb-3">{item.error_message}</p>

                    {editingId === item.id ? (
                      <div className="grid grid-cols-3 gap-4 mb-4">
                        <div>
                          <label className="text-xs text-gray-500">Date</label>
                          <Input
                            value={editValues.date}
                            onChange={(e) => setEditValues({ ...editValues, date: e.target.value })}
                            className={item.error_field === 'date' ? 'border-red-500' : ''}
                          />
                        </div>
                        <div>
                          <label className="text-xs text-gray-500">Amount</label>
                          <Input
                            value={editValues.amount}
                            onChange={(e) => setEditValues({ ...editValues, amount: e.target.value })}
                            className={item.error_field === 'amount' ? 'border-red-500' : ''}
                          />
                        </div>
                        <div>
                          <label className="text-xs text-gray-500">Description</label>
                          <Input
                            value={editValues.description}
                            onChange={(e) => setEditValues({ ...editValues, description: e.target.value })}
                          />
                        </div>
                      </div>
                    ) : (
                      <div className="grid grid-cols-3 gap-4 mb-4 text-sm">
                        <div>
                          <span className="text-gray-500">Date:</span>{' '}
                          <span className={item.error_field === 'date' ? 'text-red-600 font-medium' : ''}>
                            {item.raw_data.date || '(missing)'}
                          </span>
                        </div>
                        <div>
                          <span className="text-gray-500">Amount:</span>{' '}
                          <span className={item.error_field === 'amount' ? 'text-red-600 font-medium' : ''}>
                            {item.raw_data.amount ?? '(missing)'}
                          </span>
                        </div>
                        <div>
                          <span className="text-gray-500">Description:</span>{' '}
                          {item.raw_data.description_raw || item.raw_data.description || '(missing)'}
                        </div>
                      </div>
                    )}

                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-400">
                        From: {item.import_filename} • {new Date(item.created_at).toLocaleDateString()}
                      </span>

                      {item.status === 'PENDING' && (
                        <div className="flex gap-2">
                          {editingId === item.id ? (
                            <>
                              <Button size="sm" onClick={() => saveEdit(item.id)}>Save</Button>
                              <Button size="sm" variant="outline" onClick={() => setEditingId(null)}>Cancel</Button>
                            </>
                          ) : (
                            <>
                              <Button size="sm" variant="outline" onClick={() => startEdit(item)}>Edit</Button>
                              <Button size="sm" onClick={() => handleRetry(item.id)}>Retry</Button>
                              <Button size="sm" variant="destructive" onClick={() => handleDiscard(item.id)}>Discard</Button>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/quarantine/page.tsx
git commit -m "feat: add quarantine review page"
```

---

## Task 10: Add Quarantine Indicator to Imports Page

**Files:**
- Modify: `frontend/app/imports/page.tsx`

**Step 1: Add quarantine indicator after import success**

Find the import complete section (around line 800-850) and add a quarantine warning:

After the success message, add:

```tsx
{/* Quarantine Warning */}
{importRecords.some(r => r.transactions_quarantined > 0) && (
  <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6">
    <p className="text-amber-800 font-medium mb-2">
      Some transactions need review
    </p>
    <p className="text-amber-700 text-sm mb-3">
      {importRecords.reduce((sum, r) => sum + (r.transactions_quarantined || 0), 0)} transactions
      couldn't be imported and are waiting for your review.
    </p>
    <Link href="/quarantine">
      <Button variant="outline" size="sm">
        Review Quarantined Transactions
      </Button>
    </Link>
  </div>
)}
```

**Step 2: Update ImportRecord type to include quarantine fields**

In `frontend/lib/types.ts`, add to the ImportRecord interface:

```typescript
  transactions_quarantined?: number;
  quarantine_resolved?: boolean;
```

**Step 3: Commit**

```bash
git add frontend/app/imports/page.tsx frontend/lib/types.ts
git commit -m "feat: add quarantine indicator to imports page"
```

---

## Task 11: Add Quarantine Link to Navigation

**Files:**
- Modify: `frontend/components/nav.tsx` (or equivalent navigation component)

**Step 1: Find navigation component and add quarantine link**

Add a link to the quarantine page in the navigation, with a badge showing pending count if > 0.

**Step 2: Commit**

```bash
git add frontend/components/nav.tsx
git commit -m "feat: add quarantine link to navigation"
```

---

## Task 12: Final Integration Test

**Step 1: Start backend**

Run: `cd backend && ./venv/bin/uvicorn app.main:app --reload`

**Step 2: Start frontend**

Run: `cd frontend && npm run dev`

**Step 3: Test import with bad data**

1. Create a test CSV with some invalid rows
2. Import via UI
3. Verify quarantine count shows in response
4. Navigate to /quarantine
5. Edit a row and retry
6. Verify it moves to transactions

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: integration test fixes"
```

---

## Summary

This plan implements:
1. **QuarantinedTransaction model** - stores failed rows with error details
2. **Database migration** - creates table and adds columns to import_records
3. **QuarantineService** - business logic for list, update, retry, discard
4. **API endpoints** - full CRUD + bulk operations
5. **Import service changes** - quarantines failures instead of skipping
6. **Frontend quarantine page** - review, edit, retry, discard UI
7. **Import page integration** - shows quarantine count and link

Total: ~12 tasks, each completable in 2-5 minutes following TDD approach.
