"""Transactions API endpoints."""

from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.transaction import Transaction, TransactionType
from app.schemas.transaction import (
    TransactionCreate,
    TransactionUpdate,
    TransactionResponse,
    TransactionListResponse,
    BulkUpdateRequest
)

router = APIRouter()


@router.get("/transactions", response_model=TransactionListResponse)
def list_transactions(
    account_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    transaction_type: Optional[TransactionType] = Query(None),
    category: Optional[str] = Query(None),
    is_spend: Optional[bool] = Query(None),
    needs_review: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """List transactions with filters and pagination.

    Args:
        account_id: Filter by account ID
        start_date: Filter by date >= start_date
        end_date: Filter by date <= end_date
        transaction_type: Filter by transaction type
        category: Filter by category
        is_spend: Filter by spending flag
        needs_review: Filter by review flag
        page: Page number (1-indexed)
        page_size: Items per page
        db: Database session

    Returns:
        Paginated list of transactions
    """
    query = db.query(Transaction)

    # Apply filters
    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if transaction_type:
        query = query.filter(Transaction.transaction_type == transaction_type)
    if category:
        query = query.filter(Transaction.category == category)
    if is_spend is not None:
        query = query.filter(Transaction.is_spend == is_spend)
    if needs_review is not None:
        query = query.filter(Transaction.needs_review == needs_review)

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    transactions = query.order_by(Transaction.date.desc()).offset(offset).limit(page_size).all()

    has_more = (offset + len(transactions)) < total

    return TransactionListResponse(
        transactions=transactions,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more
    )


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: str,
    db: Session = Depends(get_db)
):
    """Get transaction by ID.

    Args:
        transaction_id: Transaction ID
        db: Database session

    Returns:
        Transaction details
    """
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction {transaction_id} not found"
        )

    return transaction


@router.put("/transactions/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: str,
    transaction_data: TransactionUpdate,
    db: Session = Depends(get_db)
):
    """Update a transaction.

    Args:
        transaction_id: Transaction ID
        transaction_data: Transaction update data
        db: Database session

    Returns:
        Updated transaction
    """
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction {transaction_id} not found"
        )

    # Update fields
    if transaction_data.transaction_type is not None:
        transaction.transaction_type = transaction_data.transaction_type
        # Re-calculate is_spend and is_income based on new type
        transaction.set_is_spend_based_on_type()

    if transaction_data.category is not None:
        transaction.category = transaction_data.category
    if transaction_data.subcategory is not None:
        transaction.subcategory = transaction_data.subcategory
    if transaction_data.tags is not None:
        transaction.tags = transaction_data.tags
    if transaction_data.user_note is not None:
        transaction.user_note = transaction_data.user_note
    if transaction_data.needs_review is not None:
        transaction.needs_review = transaction_data.needs_review

    # Mark as manually edited
    transaction.classification_method = 'MANUAL'

    db.commit()
    db.refresh(transaction)

    return transaction


@router.post("/transactions/bulk-update", response_model=dict)
def bulk_update_transactions(
    request: BulkUpdateRequest,
    db: Session = Depends(get_db)
):
    """Bulk update multiple transactions.

    Args:
        request: Bulk update request with transaction IDs and updates
        db: Database session

    Returns:
        Update summary
    """
    transactions = db.query(Transaction).filter(
        Transaction.id.in_(request.transaction_ids)
    ).all()

    if len(transactions) != len(request.transaction_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more transactions not found"
        )

    # Apply updates to all transactions
    for transaction in transactions:
        if request.updates.transaction_type is not None:
            transaction.transaction_type = request.updates.transaction_type
            transaction.set_is_spend_based_on_type()

        if request.updates.category is not None:
            transaction.category = request.updates.category
        if request.updates.subcategory is not None:
            transaction.subcategory = request.updates.subcategory
        if request.updates.tags is not None:
            transaction.tags = request.updates.tags
        if request.updates.user_note is not None:
            transaction.user_note = request.updates.user_note
        if request.updates.needs_review is not None:
            transaction.needs_review = request.updates.needs_review

        transaction.classification_method = 'MANUAL'

    db.commit()

    return {
        "updated_count": len(transactions),
        "transaction_ids": request.transaction_ids
    }


@router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: str,
    db: Session = Depends(get_db)
):
    """Delete a transaction.

    Args:
        transaction_id: Transaction ID
        db: Database session
    """
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction {transaction_id} not found"
        )

    db.delete(transaction)
    db.commit()
