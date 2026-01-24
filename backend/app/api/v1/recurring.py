"""Recurring Transactions API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from decimal import Decimal

from app.database import get_db
from app.models.recurring_transaction import RecurringTransaction, RecurringFrequency
from app.models.user import User
from app.middleware.auth import get_current_active_user
from app.schemas.recurring import (
    RecurringTransactionCreate,
    RecurringTransactionUpdate,
    RecurringTransactionResponse,
    RecurringTransactionListResponse,
    RecurringCandidatesResponse,
    RecurringCandidate,
    UpcomingRecurringResponse,
    UpcomingRecurring,
    RecurringSummary,
)
from app.services.recurring_detection_service import RecurringDetectionService

router = APIRouter()


@router.get("/recurring", response_model=RecurringTransactionListResponse)
def list_recurring_transactions(
    is_active: bool = Query(None, description="Filter by active status"),
    is_auto_detected: bool = Query(None, description="Filter by auto-detected status"),
    frequency: RecurringFrequency = Query(None, description="Filter by frequency"),
    category: str = Query(None, description="Filter by category"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all recurring transactions."""
    query = db.query(RecurringTransaction).filter(
        RecurringTransaction.user_id == current_user.id
    )

    if is_active is not None:
        query = query.filter(RecurringTransaction.is_active == is_active)
    if is_auto_detected is not None:
        query = query.filter(RecurringTransaction.is_auto_detected == is_auto_detected)
    if frequency is not None:
        query = query.filter(RecurringTransaction.frequency == frequency)
    if category is not None:
        query = query.filter(RecurringTransaction.category == category)

    recurring = query.order_by(RecurringTransaction.merchant_normalized).all()

    return RecurringTransactionListResponse(
        recurring_transactions=recurring,
        total=len(recurring)
    )


@router.post("/recurring/detect", response_model=RecurringCandidatesResponse)
def detect_recurring_transactions(
    min_transactions: int = Query(3, ge=2, description="Minimum transactions to consider"),
    min_confidence: float = Query(0.7, ge=0, le=1, description="Minimum confidence threshold"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Run detection algorithm to find recurring transaction candidates."""
    service = RecurringDetectionService(db)
    candidates = service.detect_candidates(
        user_id=current_user.id,
        min_transactions=min_transactions,
        min_confidence=min_confidence
    )

    candidate_responses = [
        RecurringCandidate(
            merchant_normalized=c["merchant_normalized"],
            expected_amount=c["expected_amount"],
            frequency=c["frequency"],
            confidence=c["confidence"],
            transaction_count=c["transaction_count"],
            avg_interval_days=c["avg_interval_days"],
            amount_variance=c["amount_variance"],
            first_date=c["first_date"],
            last_date=c["last_date"],
            sample_transaction_ids=c["sample_transaction_ids"],
        )
        for c in candidates
    ]

    return RecurringCandidatesResponse(
        candidates=candidate_responses,
        total=len(candidate_responses)
    )


@router.get("/recurring/candidates", response_model=RecurringCandidatesResponse)
def get_pending_candidates(
    min_confidence: float = Query(0.7, ge=0, le=1, description="Minimum confidence threshold"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get detected candidates that haven't been added yet."""
    service = RecurringDetectionService(db)
    all_candidates = service.detect_candidates(
        user_id=current_user.id,
        min_confidence=min_confidence
    )

    existing = db.query(RecurringTransaction.merchant_normalized).filter(
        RecurringTransaction.user_id == current_user.id,
        RecurringTransaction.is_active == True
    ).all()
    existing_merchants = {m[0] for m in existing}

    pending = [c for c in all_candidates if c["merchant_normalized"] not in existing_merchants]

    candidate_responses = [
        RecurringCandidate(
            merchant_normalized=c["merchant_normalized"],
            expected_amount=c["expected_amount"],
            frequency=c["frequency"],
            confidence=c["confidence"],
            transaction_count=c["transaction_count"],
            avg_interval_days=c["avg_interval_days"],
            amount_variance=c["amount_variance"],
            first_date=c["first_date"],
            last_date=c["last_date"],
            sample_transaction_ids=c["sample_transaction_ids"],
        )
        for c in pending
    ]

    return RecurringCandidatesResponse(
        candidates=candidate_responses,
        total=len(candidate_responses)
    )


@router.get("/recurring/upcoming", response_model=UpcomingRecurringResponse)
def get_upcoming_recurring(
    days: int = Query(30, ge=1, le=365, description="Number of days to look ahead"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get upcoming recurring payments."""
    service = RecurringDetectionService(db)
    upcoming = service.get_upcoming(user_id=current_user.id, days_ahead=days)

    total_expected = sum(Decimal(str(u["expected_amount"])) for u in upcoming)

    upcoming_responses = [
        UpcomingRecurring(
            id=u["id"],
            merchant_normalized=u["merchant_normalized"],
            expected_amount=u["expected_amount"],
            next_expected_date=u["next_expected_date"],
            days_until=u["days_until"],
            frequency=u["frequency"],
            category=u["category"],
        )
        for u in upcoming
    ]

    return UpcomingRecurringResponse(
        upcoming=upcoming_responses,
        total=len(upcoming_responses),
        total_expected_amount=total_expected
    )


@router.get("/recurring/summary", response_model=RecurringSummary)
def get_recurring_summary(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get summary of recurring transactions."""
    service = RecurringDetectionService(db)
    summary = service.get_summary(user_id=current_user.id)

    return RecurringSummary(
        total_active=summary["total_active"],
        total_monthly_cost=summary["total_monthly_cost"],
        total_yearly_cost=summary["total_yearly_cost"],
        by_category=summary["by_category"],
        by_frequency=summary["by_frequency"],
    )


@router.post("/recurring/candidates/{merchant}/accept", response_model=RecurringTransactionResponse, status_code=status.HTTP_201_CREATED)
def accept_candidate(
    merchant: str,
    category: str = Query(None, description="Category for this subscription"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Accept a detected candidate and create a recurring transaction."""
    service = RecurringDetectionService(db)
    candidates = service.detect_candidates(user_id=current_user.id)

    candidate = next(
        (c for c in candidates if c["merchant_normalized"] == merchant),
        None
    )

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No candidate found for merchant: {merchant}"
        )

    existing = db.query(RecurringTransaction).filter(
        RecurringTransaction.user_id == current_user.id,
        RecurringTransaction.merchant_normalized == merchant,
        RecurringTransaction.is_active == True
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Recurring transaction already exists for: {merchant}"
        )

    recurring = service.create_from_candidate(candidate, user_id=current_user.id)

    if category:
        recurring.category = category
        db.commit()
        db.refresh(recurring)

    return recurring


@router.post("/recurring", response_model=RecurringTransactionResponse, status_code=status.HTTP_201_CREATED)
def create_recurring_transaction(
    data: RecurringTransactionCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a recurring transaction manually."""
    existing = db.query(RecurringTransaction).filter(
        RecurringTransaction.user_id == current_user.id,
        RecurringTransaction.merchant_normalized == data.merchant_normalized,
        RecurringTransaction.is_active == True
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Active recurring transaction already exists for: {data.merchant_normalized}"
        )

    recurring = RecurringTransaction(
        user_id=current_user.id,
        merchant_normalized=data.merchant_normalized,
        expected_amount=data.expected_amount,
        amount_tolerance=data.amount_tolerance,
        frequency=data.frequency,
        next_expected_date=data.next_expected_date,
        is_active=True,
        is_auto_detected=False,
        category=data.category,
        notes=data.notes,
    )

    db.add(recurring)
    db.commit()
    db.refresh(recurring)

    return recurring


@router.get("/recurring/{recurring_id}", response_model=RecurringTransactionResponse)
def get_recurring_transaction(
    recurring_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a recurring transaction by ID."""
    recurring = db.query(RecurringTransaction).filter(
        RecurringTransaction.id == recurring_id,
        RecurringTransaction.user_id == current_user.id
    ).first()

    if not recurring:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recurring transaction {recurring_id} not found"
        )

    return recurring


@router.put("/recurring/{recurring_id}", response_model=RecurringTransactionResponse)
def update_recurring_transaction(
    recurring_id: str,
    data: RecurringTransactionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update a recurring transaction."""
    recurring = db.query(RecurringTransaction).filter(
        RecurringTransaction.id == recurring_id,
        RecurringTransaction.user_id == current_user.id
    ).first()

    if not recurring:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recurring transaction {recurring_id} not found"
        )

    if data.merchant_normalized is not None:
        recurring.merchant_normalized = data.merchant_normalized
    if data.expected_amount is not None:
        recurring.expected_amount = data.expected_amount
    if data.amount_tolerance is not None:
        recurring.amount_tolerance = data.amount_tolerance
    if data.frequency is not None:
        recurring.frequency = data.frequency
    if data.next_expected_date is not None:
        recurring.next_expected_date = data.next_expected_date
    if data.is_active is not None:
        recurring.is_active = data.is_active
    if data.category is not None:
        recurring.category = data.category
    if data.notes is not None:
        recurring.notes = data.notes

    db.commit()
    db.refresh(recurring)

    return recurring


@router.delete("/recurring/{recurring_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recurring_transaction(
    recurring_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a recurring transaction."""
    recurring = db.query(RecurringTransaction).filter(
        RecurringTransaction.id == recurring_id,
        RecurringTransaction.user_id == current_user.id
    ).first()

    if not recurring:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recurring transaction {recurring_id} not found"
        )

    db.delete(recurring)
    db.commit()
