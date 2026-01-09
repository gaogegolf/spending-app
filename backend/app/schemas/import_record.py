"""Pydantic schemas for Import Record API."""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any

from app.models.import_record import SourceType, ImportStatus


class ImportCreate(BaseModel):
    """Schema for creating an import record."""

    account_id: str
    filename: str


class ImportPreview(BaseModel):
    """Schema for import preview (after parsing, before commit)."""

    import_id: str
    filename: str
    source_type: SourceType
    detected_columns: Optional[Dict[str, str]] = None
    transactions_preview: list[Dict[str, Any]] = Field(
        ...,
        description="First 10-20 transactions for preview"
    )
    total_count: int = Field(..., description="Total transactions in file")
    duplicate_count: int = Field(default=0, description="Number of duplicates detected")
    warnings: list[str] = Field(default_factory=list)


class ColumnMapping(BaseModel):
    """Schema for user-provided column mapping (CSV only)."""

    date_column: str
    description_column: str
    amount_column: Optional[str] = None  # For single-column amount
    debit_column: Optional[str] = None   # For debit/credit columns
    credit_column: Optional[str] = None
    amount_convention: str = Field(
        default="SINGLE_COLUMN_SIGNED",
        description="SINGLE_COLUMN_SIGNED, DEBIT_CREDIT, or ABSOLUTE_WITH_TYPE"
    )


class ImportCommit(BaseModel):
    """Schema for committing an import."""

    column_mapping: Optional[ColumnMapping] = None  # Only needed for CSV with uncertain mapping


class ImportStatusResponse(BaseModel):
    """Schema for import status response."""

    id: str
    account_id: str
    source_type: SourceType
    filename: str
    status: ImportStatus
    error_message: Optional[str]
    transactions_imported: int
    transactions_duplicate: int
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class ImportListResponse(BaseModel):
    """Schema for list of imports."""

    imports: list[ImportStatusResponse]
    total: int
