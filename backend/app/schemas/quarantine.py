"""Pydantic schemas for Quarantine API."""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any

from app.models.quarantined_transaction import QuarantineErrorType, QuarantineStatus


class QuarantinedTransactionResponse(BaseModel):
    """Full details for a single quarantined transaction."""

    id: str
    import_id: str
    account_id: Optional[str] = None
    user_id: str

    raw_data: Dict[str, Any]
    error_type: QuarantineErrorType
    error_message: str
    error_field: Optional[str] = None

    retry_count: int
    status: QuarantineStatus

    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class QuarantineListResponse(BaseModel):
    """Paginated list of quarantined transactions."""

    items: list[QuarantinedTransactionResponse]
    total: int


class QuarantineUpdateRequest(BaseModel):
    """For editing a quarantined transaction before retry."""

    raw_data: Optional[Dict[str, Any]] = None
    account_id: Optional[str] = None


class QuarantineRetryResponse(BaseModel):
    """Result of a retry attempt."""

    id: str
    status: str
    error_message: Optional[str] = None
    transaction_id: Optional[str] = None


class QuarantineBulkRequest(BaseModel):
    """For bulk operations on quarantined transactions."""

    ids: list[str]


class QuarantineBulkResponse(BaseModel):
    """Result of bulk operation."""

    success_count: int
    failed_count: int
    results: list[QuarantineRetryResponse]
