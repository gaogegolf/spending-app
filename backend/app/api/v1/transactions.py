"""Transactions API endpoints."""

from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.transaction import Transaction, TransactionType
from app.models.merchant_category import MerchantCategory
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
    description: Optional[str] = Query(None, description="Search in description/merchant"),
    is_spend: Optional[bool] = Query(None),
    needs_review: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=10000),
    db: Session = Depends(get_db)
):
    """List transactions with filters and pagination.

    Args:
        account_id: Filter by account ID
        start_date: Filter by date >= start_date
        end_date: Filter by date <= end_date
        transaction_type: Filter by transaction type
        category: Filter by category
        description: Search in description_raw or merchant_normalized
        is_spend: Filter by spending flag
        needs_review: Filter by review flag
        page: Page number (1-indexed)
        page_size: Items per page
        db: Database session

    Returns:
        Paginated list of transactions
    """
    from sqlalchemy import or_

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
    if description:
        search_term = f"%{description}%"
        query = query.filter(
            or_(
                Transaction.description_raw.ilike(search_term),
                Transaction.merchant_normalized.ilike(search_term)
            )
        )
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

    # Track if category was manually changed (for learning)
    category_changed = False
    if transaction_data.category is not None and transaction_data.category != transaction.category:
        transaction.category = transaction_data.category
        category_changed = True

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

    # Learn merchant category mapping when user manually categorizes
    if category_changed and transaction.merchant_normalized and transaction.category:
        _learn_merchant_category(
            db=db,
            merchant_normalized=transaction.merchant_normalized,
            category=transaction.category,
            user_id='default_user'
        )

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


@router.post("/transactions/bulk-delete", response_model=dict)
def bulk_delete_transactions(
    transaction_ids: list[str],
    db: Session = Depends(get_db)
):
    """Bulk delete multiple transactions.

    Args:
        transaction_ids: List of transaction IDs to delete
        db: Database session

    Returns:
        Delete summary
    """
    transactions = db.query(Transaction).filter(
        Transaction.id.in_(transaction_ids)
    ).all()

    deleted_count = len(transactions)

    for transaction in transactions:
        db.delete(transaction)

    db.commit()

    return {
        "deleted_count": deleted_count,
        "transaction_ids": [t.id for t in transactions]
    }


@router.post("/transactions/reclassify-all", response_model=dict)
def reclassify_all_transactions(
    db: Session = Depends(get_db)
):
    """Re-classify all existing transactions using the latest classification logic.

    Returns:
        Summary of re-classification
    """
    from app.services.classifier.llm_classifier import LLMClassifier
    from app.services.classifier.rule_engine import RuleEngine
    from app.services.import_service import ImportService
    from app.config import settings

    # Get all transactions
    transactions = db.query(Transaction).all()

    if not transactions:
        return {
            "reclassified_count": 0,
            "message": "No transactions to reclassify"
        }

    # Initialize classifiers
    llm_classifier = LLMClassifier()
    rule_engine = RuleEngine(db)
    import_service = ImportService(db)

    reclassified_count = 0

    # Process in batches
    batch_size = 20
    for i in range(0, len(transactions), batch_size):
        batch = transactions[i:i + batch_size]

        for transaction in batch:
            # Skip payments, transfers, income, refunds (keep their type)
            if transaction.transaction_type in ['PAYMENT', 'TRANSFER', 'INCOME', 'REFUND']:
                continue

            # Convert to dict format for classification
            txn_data = {
                'date': transaction.date.isoformat(),
                'description_raw': transaction.description_raw,
                'amount': float(transaction.amount),
                'merchant_normalized': transaction.merchant_normalized,
                'currency': transaction.currency,
            }

            # Try rule engine first
            matched_rule = rule_engine.match_transaction_data(txn_data)

            if matched_rule:
                classified = rule_engine.apply_rule_to_data(matched_rule, txn_data)
            else:
                # Check learned merchant categories next
                merchant_normalized = transaction.merchant_normalized
                classified = None

                if merchant_normalized:
                    learned = db.query(MerchantCategory).filter(
                        MerchantCategory.user_id == 'default_user',
                        MerchantCategory.merchant_normalized == merchant_normalized
                    ).first()

                    if learned:
                        # Apply learned category
                        learned.times_applied += 1
                        classified = {
                            **txn_data,
                            'transaction_type': 'EXPENSE',
                            'category': learned.category,
                            'is_spend': True,
                            'is_income': False,
                            'classification_method': 'LEARNED',
                            'confidence': learned.confidence,
                            'needs_review': False
                        }

                # Try LLM if no learned category
                if not classified and settings.ENABLE_LLM_CLASSIFICATION:
                    try:
                        classified_batch = llm_classifier.classify_batch([txn_data])
                        classified = classified_batch[0] if classified_batch else None
                    except Exception:
                        classified = None

                # Fallback to keyword-based classification
                if not classified:
                    classified = import_service._default_classification(txn_data)

            # Update transaction with new classification
            if classified and 'category' in classified:
                transaction.category = classified.get('category')
                transaction.subcategory = classified.get('subcategory')
                transaction.transaction_type = classified.get('transaction_type', transaction.transaction_type)
                transaction.classification_method = classified.get('classification_method', 'RECLASSIFIED')
                transaction.confidence = classified.get('confidence', 0.7)
                reclassified_count += 1

    db.commit()

    return {
        "reclassified_count": reclassified_count,
        "total_transactions": len(transactions),
        "message": f"Successfully re-classified {reclassified_count} transactions"
    }


def _learn_merchant_category(db: Session, merchant_normalized: str, category: str, user_id: str = 'default_user'):
    """Learn or update merchant category mapping.

    When a user manually categorizes a transaction, we save the merchant → category mapping
    for future auto-categorization.

    Args:
        db: Database session
        merchant_normalized: Normalized merchant name
        category: Category name (can be custom or predefined)
        user_id: User ID (defaults to 'default_user')
    """
    import uuid
    from datetime import datetime

    # Check if mapping already exists
    existing = db.query(MerchantCategory).filter(
        MerchantCategory.user_id == user_id,
        MerchantCategory.merchant_normalized == merchant_normalized
    ).first()

    if existing:
        # Update existing mapping
        existing.category = category
        existing.updated_at = datetime.utcnow()
        existing.confidence = 1.0  # User-provided = 100% confidence
        existing.source = 'USER'
    else:
        # Create new mapping
        new_mapping = MerchantCategory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            merchant_normalized=merchant_normalized,
            category=category,
            confidence=1.0,
            source='USER',
            times_applied=0
        )
        db.add(new_mapping)

    # Note: commit happens in the calling function
