"""Statistics service for calculating spending and income summaries."""

from typing import Dict, Any, List
from datetime import date, datetime
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.account import Account


class StatsService:
    """Service for calculating financial statistics."""

    def __init__(self, db: Session):
        """Initialize stats service.

        Args:
            db: Database session
        """
        self.db = db

    def get_monthly_summary(self, year: int, month: int,
                           user_id: str = "default_user",
                           account_id: str = None) -> Dict[str, Any]:
        """Calculate monthly spending/income summary.

        CRITICAL: Only counts transactions where is_spend=true for spending totals.
        This ensures PAYMENT/TRANSFER transactions are excluded.

        Args:
            year: Year
            month: Month (1-12)
            user_id: User ID to filter by
            account_id: Optional account ID to filter by

        Returns:
            Dictionary with monthly summary
        """
        # Calculate date range
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)

        # Build base query
        query = self.db.query(Transaction).join(Account).filter(
            Account.user_id == user_id,
            Transaction.date >= start_date,
            Transaction.date < end_date
        )

        if account_id:
            query = query.filter(Transaction.account_id == account_id)

        # CRITICAL: Calculate total spending (ONLY is_spend=true)
        total_spend = self.db.query(func.sum(Transaction.amount)).join(Account).filter(
            Account.user_id == user_id,
            Transaction.date >= start_date,
            Transaction.date < end_date,
            Transaction.is_spend == True  # CRITICAL: Excludes PAYMENT/TRANSFER
        )
        if account_id:
            total_spend = total_spend.filter(Transaction.account_id == account_id)
        total_spend = float(total_spend.scalar() or 0)

        # Calculate total income
        total_income = self.db.query(func.sum(Transaction.amount)).join(Account).filter(
            Account.user_id == user_id,
            Transaction.date >= start_date,
            Transaction.date < end_date,
            Transaction.is_income == True
        )
        if account_id:
            total_income = total_income.filter(Transaction.account_id == account_id)
        total_income = float(total_income.scalar() or 0)

        # Get category breakdown (only for spending)
        category_query = self.db.query(
            Transaction.category,
            func.sum(Transaction.amount).label('total'),
            func.count(Transaction.id).label('count')
        ).join(Account).filter(
            Account.user_id == user_id,
            Transaction.date >= start_date,
            Transaction.date < end_date,
            Transaction.is_spend == True,  # Only spending transactions
            Transaction.category.isnot(None)
        )
        if account_id:
            category_query = category_query.filter(Transaction.account_id == account_id)

        category_breakdown = category_query.group_by(Transaction.category).all()

        return {
            'year': year,
            'month': month,
            'total_spend': total_spend,
            'total_income': total_income,
            'net': total_income - total_spend,
            'category_breakdown': [
                {
                    'category': cat.category,
                    'amount': float(cat.total),
                    'count': cat.count,
                    'percentage': float(float(cat.total) / float(total_spend) * 100) if total_spend > 0 else 0
                }
                for cat in category_breakdown
            ]
        }

    def get_yearly_summary(self, year: int, user_id: str = "default_user",
                          account_id: str = None) -> Dict[str, Any]:
        """Calculate yearly spending trends.

        Args:
            year: Year
            user_id: User ID
            account_id: Optional account ID

        Returns:
            Dictionary with yearly summary
        """
        monthly_data = []
        for month in range(1, 13):
            summary = self.get_monthly_summary(year, month, user_id, account_id)
            monthly_data.append({
                'month': month,
                'month_name': date(year, month, 1).strftime('%B'),
                **summary
            })

        total_spend = sum(m['total_spend'] for m in monthly_data)
        total_income = sum(m['total_income'] for m in monthly_data)

        return {
            'year': year,
            'monthly_data': monthly_data,
            'total_spend': total_spend,
            'total_income': total_income,
            'net': total_income - total_spend,
            'avg_monthly_spend': total_spend / 12 if total_spend > 0 else 0
        }

    def get_category_breakdown(self, start_date: date, end_date: date,
                               user_id: str = "default_user",
                               account_id: str = None) -> List[Dict[str, Any]]:
        """Get spending breakdown by category for a date range.

        Args:
            start_date: Start date
            end_date: End date
            user_id: User ID
            account_id: Optional account ID

        Returns:
            List of category breakdowns
        """
        query = self.db.query(
            Transaction.category,
            func.sum(Transaction.amount).label('total'),
            func.count(Transaction.id).label('count'),
            func.avg(Transaction.amount).label('avg_amount')
        ).join(Account).filter(
            Account.user_id == user_id,
            Transaction.date.between(start_date, end_date),
            Transaction.is_spend == True,  # Only spending
            Transaction.category.isnot(None)
        )

        if account_id:
            query = query.filter(Transaction.account_id == account_id)

        results = query.group_by(Transaction.category).order_by(func.sum(Transaction.amount).desc()).all()

        total = sum(float(r.total) for r in results)

        return [
            {
                'category': r.category,
                'total': float(r.total),
                'count': r.count,
                'avg_amount': float(r.avg_amount),
                'percentage': float(r.total / total * 100) if total > 0 else 0
            }
            for r in results
        ]

    def get_merchant_analysis(self, start_date: date, end_date: date,
                              user_id: str = "default_user",
                              limit: int = 20) -> List[Dict[str, Any]]:
        """Get top merchants by spending.

        Args:
            start_date: Start date
            end_date: End date
            user_id: User ID
            limit: Number of top merchants to return

        Returns:
            List of merchant analyses
        """
        results = self.db.query(
            Transaction.merchant_normalized,
            func.sum(Transaction.amount).label('total'),
            func.count(Transaction.id).label('count'),
            func.avg(Transaction.amount).label('avg_amount')
        ).join(Account).filter(
            Account.user_id == user_id,
            Transaction.date.between(start_date, end_date),
            Transaction.is_spend == True,  # Only spending
            Transaction.merchant_normalized.isnot(None)
        ).group_by(
            Transaction.merchant_normalized
        ).order_by(
            func.sum(Transaction.amount).desc()
        ).limit(limit).all()

        return [
            {
                'merchant': r.merchant_normalized,
                'total': float(r.total),
                'count': r.count,
                'avg_amount': float(r.avg_amount)
            }
            for r in results
        ]

    def get_overview(self, user_id: str = "default_user") -> Dict[str, Any]:
        """Get dashboard overview with current month and recent transactions.

        Args:
            user_id: User ID

        Returns:
            Overview dictionary
        """
        now = datetime.now()
        current_month = self.get_monthly_summary(now.year, now.month, user_id)

        # Get transactions needing review
        needs_review_count = self.db.query(func.count(Transaction.id)).join(Account).filter(
            Account.user_id == user_id,
            Transaction.needs_review == True
        ).scalar()

        return {
            'current_month': current_month,
            'needs_review_count': needs_review_count,
            'current_year': now.year,
            'current_month_num': now.month,
        }
