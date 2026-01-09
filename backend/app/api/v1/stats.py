"""Statistics API endpoints."""

from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.stats_service import StatsService

router = APIRouter()


@router.get("/stats/monthly")
def get_monthly_summary(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get monthly spending and income summary.

    Args:
        year: Year
        month: Month (1-12)
        account_id: Optional account ID to filter by
        db: Database session

    Returns:
        Monthly summary with spending, income, net, and category breakdown
    """
    stats_service = StatsService(db)

    try:
        summary = stats_service.get_monthly_summary(
            year=year,
            month=month,
            account_id=account_id
        )
        return summary

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate monthly summary: {str(e)}"
        )


@router.get("/stats/yearly")
def get_yearly_summary(
    year: int = Query(..., ge=2000, le=2100),
    account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get yearly spending trends with monthly breakdown.

    Args:
        year: Year
        account_id: Optional account ID to filter by
        db: Database session

    Returns:
        Yearly summary with monthly data
    """
    stats_service = StatsService(db)

    try:
        summary = stats_service.get_yearly_summary(
            year=year,
            account_id=account_id
        )
        return summary

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate yearly summary: {str(e)}"
        )


@router.get("/stats/category-breakdown")
def get_category_breakdown(
    start_date: date = Query(...),
    end_date: date = Query(...),
    account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get spending breakdown by category.

    Args:
        start_date: Start date
        end_date: End date
        account_id: Optional account ID to filter by
        db: Database session

    Returns:
        List of category breakdowns with amounts and percentages
    """
    stats_service = StatsService(db)

    try:
        breakdown = stats_service.get_category_breakdown(
            start_date=start_date,
            end_date=end_date,
            account_id=account_id
        )

        total_spending = sum(cat['total'] for cat in breakdown)

        return {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'total_spending': total_spending,
            'categories': breakdown
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate category breakdown: {str(e)}"
        )


@router.get("/stats/merchant-analysis")
def get_merchant_analysis(
    start_date: date = Query(...),
    end_date: date = Query(...),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get top merchants by spending.

    Args:
        start_date: Start date
        end_date: End date
        limit: Number of top merchants to return
        db: Database session

    Returns:
        List of top merchants with spending totals
    """
    stats_service = StatsService(db)

    try:
        merchants = stats_service.get_merchant_analysis(
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )

        return {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'total_merchants': len(merchants),
            'top_merchants': merchants
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze merchants: {str(e)}"
        )


@router.get("/stats/overview")
def get_overview(
    db: Session = Depends(get_db)
):
    """Get dashboard overview with current month summary.

    Args:
        db: Database session

    Returns:
        Overview with current month stats and review count
    """
    stats_service = StatsService(db)

    try:
        overview = stats_service.get_overview()
        return overview

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get overview: {str(e)}"
        )
