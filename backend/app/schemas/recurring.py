"""Pydantic schemas for Recurring Transactions API."""

from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional
from decimal import Decimal
from app.models.recurring_transaction import RecurringFrequency


class RecurringTransactionBase(BaseModel):
    """Base schema with common fields."""

    merchant_normalized: str = Field(..., min_length=1, max_length=255, description="Normalized merchant name")
    expected_amount: Decimal = Field(..., gt=0, description="Expected payment amount")
    amount_tolerance: Decimal = Field(default=5.0, ge=0, le=100, description="Percentage tolerance for amount matching")
    frequency: RecurringFrequency = Field(..., description="Payment frequency")
    category: Optional[str] = Field(None, max_length=100, description="Category for this subscription")
    notes: Optional[str] = Field(None, description="User notes about this subscription")


class RecurringTransactionCreate(RecurringTransactionBase):
    """Schema for creating a recurring transaction manually."""

    next_expected_date: Optional[date] = Field(None, description="Next expected payment date")


class RecurringTransactionUpdate(BaseModel):
    """Schema for updating a recurring transaction."""

    merchant_normalized: Optional[str] = Field(None, min_length=1, max_length=255)
    expected_amount: Optional[Decimal] = Field(None, gt=0)
    amount_tolerance: Optional[Decimal] = Field(None, ge=0, le=100)
    frequency: Optional[RecurringFrequency] = None
    next_expected_date: Optional[date] = None
    is_active: Optional[bool] = None
    category: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


class RecurringTransactionResponse(RecurringTransactionBase):
    """Schema for recurring transaction responses."""

    id: str
    user_id: str
    next_expected_date: Optional[date]
    last_transaction_id: Optional[str]
    is_active: bool
    is_auto_detected: bool
    confidence: Optional[Decimal]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RecurringTransactionListResponse(BaseModel):
    """Schema for list of recurring transactions."""

    recurring_transactions: list[RecurringTransactionResponse]
    total: int


class RecurringCandidate(BaseModel):
    """Schema for a detected recurring transaction candidate."""

    merchant_normalized: str
    expected_amount: Decimal
    frequency: RecurringFrequency
    confidence: Decimal
    transaction_count: int
    avg_interval_days: float
    amount_variance: Decimal  # Percentage variance
    first_date: date
    last_date: date
    sample_transaction_ids: list[str]


class RecurringCandidatesResponse(BaseModel):
    """Schema for list of detected candidates."""

    candidates: list[RecurringCandidate]
    total: int


class UpcomingRecurring(BaseModel):
    """Schema for upcoming recurring payment."""

    id: str
    merchant_normalized: str
    expected_amount: Decimal
    next_expected_date: date
    days_until: int
    frequency: RecurringFrequency
    category: Optional[str]


class UpcomingRecurringResponse(BaseModel):
    """Schema for list of upcoming payments."""

    upcoming: list[UpcomingRecurring]
    total: int
    total_expected_amount: Decimal


class RecurringSummary(BaseModel):
    """Schema for recurring transactions summary."""

    total_active: int
    total_monthly_cost: Decimal
    total_yearly_cost: Decimal
    by_category: list[dict]
    by_frequency: list[dict]
