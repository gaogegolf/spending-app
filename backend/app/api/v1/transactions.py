"""Transactions API endpoints."""

import csv
import io
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models.transaction import Transaction, TransactionType
from app.models.account import Account
from app.models.merchant_category import MerchantCategory
from app.models.rule import Rule
from app.models.user import User
from app.middleware.auth import get_current_active_user
from app.services.classifier.rule_engine import RuleEngine
from app.schemas.transaction import (
    TransactionCreate,
    TransactionUpdate,
    TransactionResponse,
    TransactionListResponse,
    BulkUpdateRequest
)

router = APIRouter()


@router.post("/transactions", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(
    transaction_data: TransactionCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Manually create a new transaction.

    Args:
        transaction_data: Transaction data from user
        current_user: Authenticated user
        db: Database session

    Returns:
        Created transaction
    """
    import uuid
    import hashlib

    # Verify account belongs to user
    account = db.query(Account).filter(
        Account.id == transaction_data.account_id,
        Account.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {transaction_data.account_id} not found"
        )

    # Generate deterministic dedup hash for manual transactions
    hash_input = f"manual:{transaction_data.account_id}:{transaction_data.date.isoformat()}:{transaction_data.description_raw}:{transaction_data.amount}"
    hash_dedup_key = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

    # Check for duplicate
    existing = db.query(Transaction).filter(
        Transaction.hash_dedup_key == hash_dedup_key
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A transaction with the same account, date, description, and amount already exists"
        )

    # Create transaction
    transaction = Transaction(
        id=str(uuid.uuid4()),
        account_id=transaction_data.account_id,
        import_id=None,
        hash_dedup_key=hash_dedup_key,
        date=transaction_data.date,
        post_date=transaction_data.post_date,
        description_raw=transaction_data.description_raw,
        merchant_normalized=transaction_data.merchant_normalized,
        amount=abs(transaction_data.amount),
        currency=transaction_data.currency,
        transaction_type=transaction_data.transaction_type,
        category=transaction_data.category,
        subcategory=transaction_data.subcategory,
        tags=transaction_data.tags,
        confidence=1.0,
        needs_review=False,
        classification_method='MANUAL',
        user_note=transaction_data.user_note,
    )
    transaction.set_is_spend_based_on_type()

    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    return transaction


@router.get("/transactions", response_model=TransactionListResponse)
def list_transactions(
    account_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    transaction_type: Optional[TransactionType] = Query(None),
    category: Optional[str] = Query(None),
    description: Optional[str] = Query(None, description="Search in description/merchant"),
    matched_rule_id: Optional[str] = Query(None, description="Filter by matched rule ID (historical)"),
    match_rule_pattern: Optional[str] = Query(None, description="Filter by rule pattern (dynamic matching)"),
    is_spend: Optional[bool] = Query(None),
    needs_review: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=10000),
    current_user: User = Depends(get_current_active_user),
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
        matched_rule_id: Filter by matched rule ID (historical - stored in transaction)
        match_rule_pattern: Filter by rule pattern (dynamic - applies rule matching logic)
        is_spend: Filter by spending flag
        needs_review: Filter by review flag
        page: Page number (1-indexed)
        page_size: Items per page
        current_user: Authenticated user
        db: Database session

    Returns:
        Paginated list of transactions
    """
    from sqlalchemy import or_

    # Base query: only user's transactions via Account join
    query = db.query(Transaction).join(Account).filter(Account.user_id == current_user.id)

    # Apply filters
    if account_id:
        # Verify account belongs to user (already filtered above, but be explicit)
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
    if matched_rule_id:
        query = query.filter(Transaction.matched_rule_id == matched_rule_id)

    # Handle dynamic rule pattern matching (requires in-memory filtering)
    if match_rule_pattern:
        rule = db.query(Rule).filter(Rule.id == match_rule_pattern).first()
        if rule:
            rule_engine = RuleEngine(db)
            # Get all transactions matching other filters first
            all_transactions = query.order_by(Transaction.date.desc()).all()
            # Filter by rule pattern in memory
            matching_transactions = [
                t for t in all_transactions
                if rule_engine._rule_matches(rule, t)
            ]
            total = len(matching_transactions)
            # Apply pagination
            offset = (page - 1) * page_size
            transactions = matching_transactions[offset:offset + page_size]
            has_more = (offset + len(transactions)) < total
        else:
            # Rule not found, return empty
            total = 0
            transactions = []
            has_more = False
    else:
        # Standard SQL-based filtering
        total = query.count()
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


@router.get("/transactions/export")
def export_transactions(
    account_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    transaction_type: Optional[TransactionType] = Query(None),
    category: Optional[str] = Query(None),
    description: Optional[str] = Query(None, description="Search in description/merchant"),
    match_rule_pattern: Optional[str] = Query(None, description="Filter by rule pattern"),
    format: str = Query("csv", description="Export format: csv"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Export transactions as CSV file.

    Supports the same filters as list_transactions.

    Args:
        account_id: Filter by account ID
        start_date: Filter by date >= start_date
        end_date: Filter by date <= end_date
        transaction_type: Filter by transaction type
        category: Filter by category
        description: Search in description_raw or merchant_normalized
        match_rule_pattern: Filter by rule pattern (dynamic matching)
        format: Export format (currently only CSV supported)
        current_user: Authenticated user
        db: Database session

    Returns:
        CSV file download
    """
    # Base query: only user's transactions via Account join
    query = db.query(Transaction).join(Account).filter(Account.user_id == current_user.id)

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

    # Handle dynamic rule pattern matching
    if match_rule_pattern:
        rule = db.query(Rule).filter(Rule.id == match_rule_pattern).first()
        if rule:
            rule_engine = RuleEngine(db)
            all_transactions = query.order_by(Transaction.date.desc()).all()
            transactions = [
                t for t in all_transactions
                if rule_engine._rule_matches(rule, t)
            ]
        else:
            transactions = []
    else:
        # Get all matching transactions
        transactions = query.order_by(Transaction.date.desc()).all()

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        'Date',
        'Description',
        'Merchant',
        'Amount',
        'Type',
        'Category',
        'Subcategory',
        'Is Spend',
        'Is Income',
        'Classification Method',
        'Account ID',
        'Tags',
        'Notes'
    ])

    # Write data rows
    for txn in transactions:
        writer.writerow([
            txn.date.isoformat() if txn.date else '',
            txn.description_raw or '',
            txn.merchant_normalized or '',
            str(txn.amount) if txn.amount else '0',
            txn.transaction_type.value if txn.transaction_type else '',
            txn.category or '',
            txn.subcategory or '',
            'Yes' if txn.is_spend else 'No',
            'Yes' if txn.is_income else 'No',
            txn.classification_method.value if txn.classification_method else '',
            txn.account_id or '',
            ','.join(txn.tags) if txn.tags else '',
            txn.user_note or ''
        ])

    # Reset stream position
    output.seek(0)

    # Generate filename with date range
    filename = "transactions"
    if start_date:
        filename += f"_from_{start_date.isoformat()}"
    if end_date:
        filename += f"_to_{end_date.isoformat()}"
    filename += ".csv"

    # Return as streaming response
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get transaction by ID.

    Args:
        transaction_id: Transaction ID
        current_user: Authenticated user
        db: Database session

    Returns:
        Transaction details
    """
    # Verify transaction belongs to user via Account
    transaction = db.query(Transaction).join(Account).filter(
        Transaction.id == transaction_id,
        Account.user_id == current_user.id
    ).first()

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
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update a transaction.

    Args:
        transaction_id: Transaction ID
        transaction_data: Transaction update data
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated transaction
    """
    # Verify transaction belongs to user via Account
    transaction = db.query(Transaction).join(Account).filter(
        Transaction.id == transaction_id,
        Account.user_id == current_user.id
    ).first()

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
            user_id=current_user.id
        )

    db.commit()
    db.refresh(transaction)

    return transaction


@router.post("/transactions/bulk-update", response_model=dict)
def bulk_update_transactions(
    request: BulkUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Bulk update multiple transactions.

    Args:
        request: Bulk update request with transaction IDs and updates
        current_user: Authenticated user
        db: Database session

    Returns:
        Update summary
    """
    # Verify all transactions belong to user via Account join
    transactions = db.query(Transaction).join(Account).filter(
        Transaction.id.in_(request.transaction_ids),
        Account.user_id == current_user.id
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
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a transaction.

    Args:
        transaction_id: Transaction ID
        current_user: Authenticated user
        db: Database session
    """
    # Verify transaction belongs to user via Account
    transaction = db.query(Transaction).join(Account).filter(
        Transaction.id == transaction_id,
        Account.user_id == current_user.id
    ).first()

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
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Bulk delete multiple transactions.

    Args:
        transaction_ids: List of transaction IDs to delete
        current_user: Authenticated user
        db: Database session

    Returns:
        Delete summary
    """
    # Verify all transactions belong to user via Account join
    transactions = db.query(Transaction).join(Account).filter(
        Transaction.id.in_(transaction_ids),
        Account.user_id == current_user.id
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
    current_user: User = Depends(get_current_active_user),
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

    # Get only user's transactions via Account join
    transactions = db.query(Transaction).join(Account).filter(
        Account.user_id == current_user.id
    ).all()

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
            if transaction.transaction_type in ['TRANSFER', 'INCOME']:
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
                        MerchantCategory.user_id == current_user.id,
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


def _learn_merchant_category(db: Session, merchant_normalized: str, category: str, user_id: str):
    """Learn or update merchant category mapping.

    When a user manually categorizes a transaction, we save the merchant → category mapping
    for future auto-categorization.

    Args:
        db: Database session
        merchant_normalized: Normalized merchant name
        category: Category name (can be custom or predefined)
        user_id: User ID
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


@router.get("/transactions/merchant-count/{merchant_normalized}", response_model=dict)
def get_merchant_transaction_count(
    merchant_normalized: str,
    exclude_transaction_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get count of transactions with a specific merchant.

    Args:
        merchant_normalized: The normalized merchant name
        exclude_transaction_id: Optional transaction ID to exclude from count
        current_user: Authenticated user
        db: Database session

    Returns:
        Count of matching transactions
    """
    # Only count user's transactions via Account join
    query = db.query(Transaction).join(Account).filter(
        Transaction.merchant_normalized == merchant_normalized,
        Account.user_id == current_user.id
    )

    if exclude_transaction_id:
        query = query.filter(Transaction.id != exclude_transaction_id)

    count = query.count()

    return {
        "merchant": merchant_normalized,
        "count": count,
        "message": f"Found {count} other transactions from {merchant_normalized}"
    }


@router.post("/transactions/apply-merchant-category", response_model=dict)
def apply_category_to_merchant_transactions(
    merchant_normalized: str = Query(...),
    category: str = Query(...),
    exclude_transaction_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Apply a category to all transactions with a specific merchant.

    Args:
        merchant_normalized: The normalized merchant name
        category: The category to apply
        exclude_transaction_id: Optional transaction ID to exclude
        current_user: Authenticated user
        db: Database session

    Returns:
        Count of updated transactions
    """
    # Only update user's transactions via Account join
    query = db.query(Transaction).join(Account).filter(
        Transaction.merchant_normalized == merchant_normalized,
        Account.user_id == current_user.id
    )

    if exclude_transaction_id:
        query = query.filter(Transaction.id != exclude_transaction_id)

    transactions = query.all()

    for txn in transactions:
        txn.category = category
        txn.classification_method = 'LEARNED'

    db.commit()

    return {
        "merchant": merchant_normalized,
        "category": category,
        "updated_count": len(transactions),
        "message": f"Applied '{category}' to {len(transactions)} transactions from {merchant_normalized}"
    }
