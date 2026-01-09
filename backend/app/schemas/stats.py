"""Pydantic schemas for Statistics API."""

from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal


class MonthlySummary(BaseModel):
    """Schema for monthly spending summary."""

    year: int
    month: int
    total_spending: Decimal = Field(..., description="Sum of is_spend=true transactions")
    total_income: Decimal = Field(..., description="Sum of is_income=true transactions")
    net_change: Decimal = Field(..., description="Income - Spending")
    transaction_count: int
    spending_count: int = Field(..., description="Number of transactions with is_spend=true")
    income_count: int = Field(..., description="Number of transactions with is_income=true")
    top_category: Optional[str] = Field(None, description="Category with highest spending")
    top_category_amount: Optional[Decimal] = None


class CategoryBreakdown(BaseModel):
    """Schema for category spending breakdown."""

    category: str
    amount: Decimal
    transaction_count: int
    percentage: Decimal = Field(..., ge=0, le=100, description="Percentage of total spending")


class CategoryBreakdownResponse(BaseModel):
    """Schema for category breakdown response."""

    start_date: Optional[str]
    end_date: Optional[str]
    total_spending: Decimal
    categories: list[CategoryBreakdown]


class MerchantSummary(BaseModel):
    """Schema for merchant spending summary."""

    merchant: str
    amount: Decimal
    transaction_count: int
    avg_transaction: Decimal
    first_transaction: str = Field(..., description="Date of first transaction")
    last_transaction: str = Field(..., description="Date of last transaction")


class MerchantAnalysisResponse(BaseModel):
    """Schema for merchant analysis response."""

    start_date: Optional[str]
    end_date: Optional[str]
    total_merchants: int
    top_merchants: list[MerchantSummary]


class YearlySummary(BaseModel):
    """Schema for yearly summary."""

    year: int
    total_spending: Decimal
    total_income: Decimal
    net_change: Decimal
    monthly_breakdown: list[MonthlySummary]


class SpendingTrend(BaseModel):
    """Schema for spending trends over time."""

    period: str = Field(..., description="Month in YYYY-MM format")
    spending: Decimal
    income: Decimal
    transaction_count: int


class SpendingTrendsResponse(BaseModel):
    """Schema for spending trends response."""

    periods: list[SpendingTrend]
    average_monthly_spending: Decimal
    average_monthly_income: Decimal
