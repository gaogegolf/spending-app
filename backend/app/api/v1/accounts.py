"""Accounts API endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import Account
from app.schemas.account import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    AccountListResponse
)

router = APIRouter()


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    account_data: AccountCreate,
    db: Session = Depends(get_db)
):
    """Create a new account.

    Args:
        account_data: Account creation data
        db: Database session

    Returns:
        Created account
    """
    account = Account(
        name=account_data.name,
        institution=account_data.institution,
        account_type=account_data.account_type,
        account_number_last4=account_data.account_number_last4,
        currency=account_data.currency
    )

    db.add(account)
    db.commit()
    db.refresh(account)

    return account


@router.get("/accounts", response_model=AccountListResponse)
def list_accounts(
    is_active: bool = None,
    db: Session = Depends(get_db)
):
    """List all accounts.

    Args:
        is_active: Filter by active status (optional)
        db: Database session

    Returns:
        List of accounts
    """
    query = db.query(Account)

    if is_active is not None:
        query = query.filter(Account.is_active == is_active)

    accounts = query.order_by(Account.created_at.desc()).all()

    return AccountListResponse(
        accounts=accounts,
        total=len(accounts)
    )


@router.get("/accounts/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: str,
    db: Session = Depends(get_db)
):
    """Get account by ID.

    Args:
        account_id: Account ID
        db: Database session

    Returns:
        Account details
    """
    account = db.query(Account).filter(Account.id == account_id).first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found"
        )

    return account


@router.put("/accounts/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: str,
    account_data: AccountUpdate,
    db: Session = Depends(get_db)
):
    """Update an account.

    Args:
        account_id: Account ID
        account_data: Account update data
        db: Database session

    Returns:
        Updated account
    """
    account = db.query(Account).filter(Account.id == account_id).first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found"
        )

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

    return account


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: str,
    db: Session = Depends(get_db)
):
    """Delete an account (soft delete by setting is_active=False).

    Args:
        account_id: Account ID
        db: Database session
    """
    account = db.query(Account).filter(Account.id == account_id).first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found"
        )

    # Soft delete
    account.is_active = False
    db.commit()
