"""Accounts API endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.import_record import ImportRecord
from app.models.holdings_snapshot import HoldingsSnapshot
from app.models.position import Position
from app.models.user import User
from app.middleware.auth import get_current_active_user
from app.schemas.account import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    AccountListResponse
)

router = APIRouter()


def _get_account_stats(db: Session, account_id: str) -> dict:
    """Get stats for a single account (transaction count, import count, snapshot count, position count)."""
    from sqlalchemy import desc

    # Transaction count
    transaction_count = db.query(func.count(Transaction.id)).filter(
        Transaction.account_id == account_id
    ).scalar() or 0

    # Import count (statements imported)
    import_count = db.query(func.count(ImportRecord.id)).filter(
        ImportRecord.account_id == account_id
    ).scalar() or 0

    # Snapshot count
    snapshot_count = db.query(func.count(HoldingsSnapshot.id)).filter(
        HoldingsSnapshot.account_id == account_id
    ).scalar() or 0

    # Position count (from latest snapshot)
    position_count = 0
    latest_snapshot = db.query(HoldingsSnapshot.id).filter(
        HoldingsSnapshot.account_id == account_id
    ).order_by(desc(HoldingsSnapshot.statement_date)).first()
    if latest_snapshot:
        position_count = db.query(func.count(Position.id)).filter(
            Position.snapshot_id == latest_snapshot[0]
        ).scalar() or 0

    return {
        'transaction_count': transaction_count,
        'import_count': import_count,
        'snapshot_count': snapshot_count,
        'position_count': position_count,
    }


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    account_data: AccountCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new account.

    Args:
        account_data: Account creation data
        current_user: Authenticated user
        db: Database session

    Returns:
        Created account
    """
    account = Account(
        user_id=current_user.id,
        name=account_data.name,
        institution=account_data.institution,
        account_type=account_data.account_type,
        account_number_last4=account_data.account_number_last4,
        currency=account_data.currency
    )

    db.add(account)
    db.commit()
    db.refresh(account)

    response = AccountResponse.model_validate(account)
    response.transaction_count = 0  # New account has no transactions

    return response


@router.get("/accounts", response_model=AccountListResponse)
def list_accounts(
    is_active: bool = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all accounts.

    Args:
        is_active: Filter by active status (optional)
        current_user: Authenticated user
        db: Database session

    Returns:
        List of accounts with transaction/snapshot/position counts
    """
    query = db.query(Account).filter(Account.user_id == current_user.id)

    if is_active is not None:
        query = query.filter(Account.is_active == is_active)

    accounts = query.order_by(Account.created_at.desc()).all()

    # Get transaction counts for all accounts in one query
    transaction_counts = dict(
        db.query(Transaction.account_id, func.count(Transaction.id))
        .group_by(Transaction.account_id)
        .all()
    )

    # Get import counts (number of statements imported) for all accounts
    import_counts = dict(
        db.query(ImportRecord.account_id, func.count(ImportRecord.id))
        .group_by(ImportRecord.account_id)
        .all()
    )

    # Get snapshot counts for all accounts
    snapshot_counts = dict(
        db.query(HoldingsSnapshot.account_id, func.count(HoldingsSnapshot.id))
        .group_by(HoldingsSnapshot.account_id)
        .all()
    )

    # Get latest snapshot ID for each account (for position counts)
    from sqlalchemy import desc
    latest_snapshots = {}
    for account in accounts:
        latest = db.query(HoldingsSnapshot.id).filter(
            HoldingsSnapshot.account_id == account.id
        ).order_by(desc(HoldingsSnapshot.statement_date)).first()
        if latest:
            latest_snapshots[account.id] = latest[0]

    # Get position counts for latest snapshots
    position_counts = {}
    if latest_snapshots:
        snapshot_ids = list(latest_snapshots.values())
        position_query = (
            db.query(Position.snapshot_id, func.count(Position.id))
            .filter(Position.snapshot_id.in_(snapshot_ids))
            .group_by(Position.snapshot_id)
            .all()
        )
        snapshot_to_positions = dict(position_query)
        # Map back to account_id
        for account_id, snapshot_id in latest_snapshots.items():
            position_counts[account_id] = snapshot_to_positions.get(snapshot_id, 0)

    # Build response with all counts
    account_responses = []
    for account in accounts:
        response = AccountResponse.model_validate(account)
        response.transaction_count = transaction_counts.get(account.id, 0)
        response.import_count = import_counts.get(account.id, 0)
        response.snapshot_count = snapshot_counts.get(account.id, 0)
        response.position_count = position_counts.get(account.id, 0)
        account_responses.append(response)

    return AccountListResponse(
        accounts=account_responses,
        total=len(account_responses)
    )


@router.get("/accounts/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get account by ID.

    Args:
        account_id: Account ID
        current_user: Authenticated user
        db: Database session

    Returns:
        Account details with all stats
    """
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found"
        )

    stats = _get_account_stats(db, account_id)
    response = AccountResponse.model_validate(account)
    response.transaction_count = stats['transaction_count']
    response.import_count = stats['import_count']
    response.snapshot_count = stats['snapshot_count']
    response.position_count = stats['position_count']

    return response


# Define account type categories
BANK_ACCOUNT_TYPES = {'CREDIT_CARD', 'CHECKING', 'SAVINGS', 'OTHER'}
BROKERAGE_ACCOUNT_TYPES = {'BROKERAGE', 'IRA_ROTH', 'IRA_TRADITIONAL', 'RETIREMENT_401K', 'STOCK_PLAN'}


def get_account_category(account_type: str) -> str:
    """Get the category (bank or brokerage) for an account type."""
    if account_type in BANK_ACCOUNT_TYPES:
        return 'bank'
    elif account_type in BROKERAGE_ACCOUNT_TYPES:
        return 'brokerage'
    return 'other'


@router.put("/accounts/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: str,
    account_data: AccountUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update an account.

    Args:
        account_id: Account ID
        account_data: Account update data
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated account
    """
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found"
        )

    # Validate account_type change - must stay in same category
    if account_data.account_type is not None:
        current_category = get_account_category(account.account_type.value)
        new_category = get_account_category(account_data.account_type.value)
        if current_category != new_category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot change account type from {current_category} to {new_category} category"
            )
        account.account_type = account_data.account_type

    # Update fields
    if account_data.name is not None:
        account.name = account_data.name
    if account_data.institution is not None:
        account.institution = account_data.institution
    if account_data.account_number_last4 is not None:
        account.account_number_last4 = account_data.account_number_last4
    if account_data.is_active is not None:
        account.is_active = account_data.is_active

    db.commit()
    db.refresh(account)

    stats = _get_account_stats(db, account_id)
    response = AccountResponse.model_validate(account)
    response.transaction_count = stats['transaction_count']
    response.import_count = stats['import_count']
    response.snapshot_count = stats['snapshot_count']
    response.position_count = stats['position_count']

    return response


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: str,
    permanent: bool = Query(False, description="If true, permanently delete account and all data"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete an account.

    Args:
        account_id: Account ID
        permanent: If true, permanently delete. If false, soft delete (deactivate).
        current_user: Authenticated user
        db: Database session
    """
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found"
        )

    if permanent:
        # Hard delete - remove all associated data
        from app.models.transaction import Transaction
        from app.models.import_record import ImportRecord
        from app.models.holdings_snapshot import HoldingsSnapshot
        from app.models.position import Position

        # Delete positions for any snapshots
        snapshots = db.query(HoldingsSnapshot).filter(HoldingsSnapshot.account_id == account_id).all()
        snapshot_ids = [s.id for s in snapshots]
        if snapshot_ids:
            db.query(Position).filter(Position.snapshot_id.in_(snapshot_ids)).delete(synchronize_session=False)

        # Delete snapshots
        db.query(HoldingsSnapshot).filter(HoldingsSnapshot.account_id == account_id).delete(synchronize_session=False)

        # Delete transactions
        db.query(Transaction).filter(Transaction.account_id == account_id).delete(synchronize_session=False)

        # Delete import records
        db.query(ImportRecord).filter(ImportRecord.account_id == account_id).delete(synchronize_session=False)

        # Delete account
        db.delete(account)
    else:
        # Soft delete
        account.is_active = False

    db.commit()
