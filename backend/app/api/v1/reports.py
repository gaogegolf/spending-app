"""Reports API endpoints for YoY comparisons and exports."""

from datetime import date, datetime
from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.middleware.auth import get_current_active_user
from app.services.stats_service import StatsService
from app.services.export_service import ExportService
from app.schemas.reports import (
    YoYComparisonResponse,
    YoYMonthlyComparisonResponse,
    SpendingVelocityResponse,
)

router = APIRouter()


@router.get("/stats/yoy", response_model=YoYComparisonResponse)
def get_yoy_comparison(
    year1: int = Query(..., description="First year (typically earlier)"),
    year2: int = Query(..., description="Second year (typically later/current)"),
    account_id: str = Query(None, description="Filter by account"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get year-over-year spending comparison."""
    service = StatsService(db)
    return service.get_yoy_comparison(year1, year2, current_user.id, account_id)


@router.get("/stats/yoy/monthly", response_model=YoYMonthlyComparisonResponse)
def get_yoy_monthly_comparison(
    month: int = Query(..., ge=1, le=12, description="Month to compare (1-12)"),
    year1: int = Query(..., description="First year"),
    year2: int = Query(..., description="Second year"),
    account_id: str = Query(None, description="Filter by account"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Compare the same month across two years."""
    service = StatsService(db)
    return service.get_yoy_monthly_comparison(month, year1, year2, current_user.id, account_id)


@router.get("/stats/velocity", response_model=SpendingVelocityResponse)
def get_spending_velocity(
    months: int = Query(12, ge=3, le=36, description="Number of months to analyze"),
    account_id: str = Query(None, description="Filter by account"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get spending velocity (trend) over recent months."""
    service = StatsService(db)
    return service.get_spending_velocity(current_user.id, months, account_id)


@router.get("/reports/export")
def export_report(
    format: str = Query("csv", description="Export format: csv, excel, or pdf"),
    start_date: date = Query(None, description="Start date"),
    end_date: date = Query(None, description="End date"),
    account_id: str = Query(None, description="Filter by account"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Export financial report in specified format."""
    service = ExportService(db)

    date_suffix = datetime.now().strftime('%Y%m%d')
    base_filename = f"finance_report_{date_suffix}"

    if format == "csv":
        content = service.export_to_csv(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            account_id=account_id
        )
        return StreamingResponse(
            iter([content.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={base_filename}.csv"
            }
        )

    elif format == "excel":
        content = service.export_to_excel(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            account_id=account_id
        )
        return StreamingResponse(
            content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={base_filename}.xlsx"
            }
        )

    elif format == "pdf":
        content = service.export_to_pdf(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            account_id=account_id
        )
        return StreamingResponse(
            content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={base_filename}.pdf"
            }
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format: {format}. Supported formats: csv, excel, pdf"
        )
