"""Pydantic schemas for Transaction API."""

from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional
from decimal import Decimal

from app.models.transaction import TransactionType, ClassificationMethod


class TransactionBase(BaseModel):
    """Base transaction schema with common fields."""

    date: date
    description_raw: str
    amount: Decimal = Field(..., description="Transaction amount (can be negative for expenses in some formats)")
    currency: str = Field(default="USD", min_length=3, max_length=3)


class TransactionCreate(TransactionBase):
    """Schema for creating a new transaction."""

    account_id: str
    post_date: Optional[date] = None
    merchant_normalized: Optional[str] = None
    transaction_type: TransactionType
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    is_spend: bool = False
    is_income: bool = False
    confidence: Optional[Decimal] = Field(None, ge=0, le=1)
    needs_review: bool = False
    user_note: Optional[str] = None


class TransactionUpdate(BaseModel):
    """Schema for updating a transaction."""

    transaction_type: Optional[TransactionType] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: Optional[list[str]] = None
    user_note: Optional[str] = None
    needs_review: Optional[bool] = None


class TransactionResponse(TransactionBase):
    """Schema for transaction responses."""

    id: str
    account_id: str
    import_id: Optional[str]
    post_date: Optional[date]
    merchant_normalized: Optional[str]
    transaction_type: TransactionType
    category: Optional[str]
    subcategory: Optional[str]
    tags: list[str]
    is_spend: bool
    is_income: bool
    confidence: Optional[Decimal]
    needs_review: bool
    reviewed_at: Optional[datetime]
    matched_rule_id: Optional[str]
    classification_method: Optional[ClassificationMethod]
    user_note: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TransactionFilter(BaseModel):
    """Schema for filtering transactions."""

    account_id: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    transaction_type: Optional[TransactionType] = None
    category: Optional[str] = None
    is_spend: Optional[bool] = None
    needs_review: Optional[bool] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)


class TransactionListResponse(BaseModel):
    """Schema for paginated transaction list."""

    transactions: list[TransactionResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class BulkUpdateRequest(BaseModel):
    """Schema for bulk updating transactions."""

    transaction_ids: list[str] = Field(..., min_length=1)
    updates: TransactionUpdate
