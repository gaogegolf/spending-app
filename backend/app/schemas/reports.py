"""Pydantic schemas for Reports API."""

from pydantic import BaseModel, Field
from datetime import date
from typing import Optional, List


class YoYComparisonMonth(BaseModel):
    """Monthly YoY comparison data."""

    month: int
    month_name: str
    year1_spend: float
    year2_spend: float
    change: float
    change_pct: float


class YoYComparisonResponse(BaseModel):
    """Year-over-year comparison response."""

    year1: int
    year2: int
    year1_total_spend: float
    year2_total_spend: float
    spend_change: float
    spend_change_pct: float
    year1_total_income: float
    year2_total_income: float
    income_change: float
    income_change_pct: float
    monthly_comparison: List[YoYComparisonMonth]


class CategoryYoYComparison(BaseModel):
    """Category comparison between two periods."""

    category: str
    year1_amount: float
    year2_amount: float
    change: float
    change_pct: float


class YoYMonthlyComparisonResponse(BaseModel):
    """Same month year-over-year comparison."""

    month: int
    month_name: str
    year1: int
    year2: int
    year1_summary: dict
    year2_summary: dict
    spend_change: float
    spend_change_pct: float
    category_comparison: List[CategoryYoYComparison]


class VelocityMonth(BaseModel):
    """Monthly velocity data point."""

    year: int
    month: int
    month_name: str
    total_spend: float
    total_income: float
    net: float


class SpendingVelocityResponse(BaseModel):
    """Spending velocity (trend) response."""

    months_analyzed: int
    monthly_data: List[VelocityMonth]
    avg_monthly_spend: float
    avg_monthly_income: float
    avg_monthly_net: float
    trend_slope: float
    trend_direction: str  # 'increasing', 'decreasing', 'stable'


class ExportRequest(BaseModel):
    """Request for exporting a report."""

    start_date: Optional[date] = Field(None, description="Start date for the report")
    end_date: Optional[date] = Field(None, description="End date for the report")
    account_id: Optional[str] = Field(None, description="Filter by account")
    format: str = Field("csv", description="Export format: csv, excel, or pdf")
