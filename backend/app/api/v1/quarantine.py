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
from app.models.quarantined_transaction import QuarantinedTransaction, QuarantineStatus
from app.models.user import User
from app.middleware.auth import get_current_active_user

router = APIRouter()


def _to_response(item: QuarantinedTransaction) -> QuarantinedTransactionResponse:
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
    filter_status: Optional[QuarantineStatus] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List quarantined transactions for current user."""
    service = QuarantineService(db, current_user.id)
    items, total, pending_count = service.list_quarantined(
        import_id=import_id,
        status=filter_status,
        limit=limit,
        offset=offset,
    )

    return QuarantineListResponse(
        items=[_to_response(item) for item in items],
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

    return _to_response(item)


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

    return _to_response(item)


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

    return _to_response(item)


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
        failed_count=sum(1 for _, success, _, _ in results if not success),
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
        failed_count=sum(1 for _, success, _ in results if not success),
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
