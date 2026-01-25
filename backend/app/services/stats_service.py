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
                           user_id: str,
                           account_id: str = None) -> Dict[str, Any]:
        """Calculate monthly spending/income summary.

        CRITICAL: Only counts transactions where is_spend=true for spending totals.
        This ensures TRANSFER and UNCATEGORIZED transactions are excluded.

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
            Transaction.is_spend == True  # CRITICAL: Excludes TRANSFER/UNCATEGORIZED
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

        # Income is stored as negative, convert to positive for display
        total_income_positive = abs(total_income)

        return {
            'year': year,
            'month': month,
            'total_spend': total_spend,
            'total_income': total_income_positive,
            'net': total_income_positive - total_spend,
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

    def get_yearly_summary(self, year: int, user_id: str,
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
        total_income = sum(m['total_income'] for m in monthly_data)  # Already positive from monthly

        return {
            'year': year,
            'monthly_data': monthly_data,
            'total_spend': total_spend,
            'total_income': total_income,
            'net': total_income - total_spend,  # Both values already positive
            'avg_monthly_spend': total_spend / 12 if total_spend > 0 else 0
        }

    def get_category_breakdown(self, start_date: date, end_date: date,
                               user_id: str,
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
                              user_id: str,
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

    def get_date_range_summary(self, start_date: date, end_date: date,
                                user_id: str,
                                account_id: str = None) -> Dict[str, Any]:
        """Calculate summary for a custom date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            user_id: User ID to filter by
            account_id: Optional account ID to filter by

        Returns:
            Dictionary with date range summary including totals and category breakdown
        """
        # Calculate total spending (ONLY is_spend=true)
        total_spend = self.db.query(func.sum(Transaction.amount)).join(Account).filter(
            Account.user_id == user_id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.is_spend == True
        )
        if account_id:
            total_spend = total_spend.filter(Transaction.account_id == account_id)
        total_spend = float(total_spend.scalar() or 0)

        # Calculate total income
        total_income = self.db.query(func.sum(Transaction.amount)).join(Account).filter(
            Account.user_id == user_id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.is_income == True
        )
        if account_id:
            total_income = total_income.filter(Transaction.account_id == account_id)
        total_income = float(total_income.scalar() or 0)

        # Get transaction count
        txn_count = self.db.query(func.count(Transaction.id)).join(Account).filter(
            Account.user_id == user_id,
            Transaction.date >= start_date,
            Transaction.date <= end_date
        )
        if account_id:
            txn_count = txn_count.filter(Transaction.account_id == account_id)
        txn_count = txn_count.scalar() or 0

        # Get category breakdown (only for spending)
        category_query = self.db.query(
            Transaction.category,
            func.sum(Transaction.amount).label('total'),
            func.count(Transaction.id).label('count')
        ).join(Account).filter(
            Account.user_id == user_id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.is_spend == True,
            Transaction.category.isnot(None)
        )
        if account_id:
            category_query = category_query.filter(Transaction.account_id == account_id)

        category_breakdown = category_query.group_by(Transaction.category).order_by(
            func.sum(Transaction.amount).desc()
        ).all()

        # Income is stored as negative, convert to positive for display
        total_income_positive = abs(total_income)

        return {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'total_spend': total_spend,
            'total_income': total_income_positive,
            'net': total_income_positive - total_spend,
            'transaction_count': txn_count,
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

    def get_overview(self, user_id: str) -> Dict[str, Any]:
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

    def get_yoy_comparison(self, year1: int, year2: int,
                           user_id: str,
                           account_id: str = None) -> Dict[str, Any]:
        """Compare spending between two years (year-over-year).

        Args:
            year1: First year (typically earlier)
            year2: Second year (typically later/current)
            user_id: User ID
            account_id: Optional account ID

        Returns:
            Dictionary with YoY comparison data
        """
        summary1 = self.get_yearly_summary(year1, user_id, account_id)
        summary2 = self.get_yearly_summary(year2, user_id, account_id)

        spend_change = summary2['total_spend'] - summary1['total_spend']
        spend_change_pct = (spend_change / summary1['total_spend'] * 100) if summary1['total_spend'] > 0 else 0

        income_change = summary2['total_income'] - summary1['total_income']
        income_change_pct = (income_change / summary1['total_income'] * 100) if summary1['total_income'] > 0 else 0

        # Monthly comparison
        monthly_comparison = []
        for i in range(12):
            m1 = summary1['monthly_data'][i]
            m2 = summary2['monthly_data'][i]
            change = m2['total_spend'] - m1['total_spend']
            change_pct = (change / m1['total_spend'] * 100) if m1['total_spend'] > 0 else 0

            monthly_comparison.append({
                'month': i + 1,
                'month_name': m1['month_name'],
                'year1_spend': m1['total_spend'],
                'year2_spend': m2['total_spend'],
                'change': change,
                'change_pct': change_pct,
            })

        return {
            'year1': year1,
            'year2': year2,
            'year1_total_spend': summary1['total_spend'],
            'year2_total_spend': summary2['total_spend'],
            'spend_change': spend_change,
            'spend_change_pct': spend_change_pct,
            'year1_total_income': summary1['total_income'],
            'year2_total_income': summary2['total_income'],
            'income_change': income_change,
            'income_change_pct': income_change_pct,
            'monthly_comparison': monthly_comparison,
        }

    def get_yoy_monthly_comparison(self, month: int, year1: int, year2: int,
                                   user_id: str,
                                   account_id: str = None) -> Dict[str, Any]:
        """Compare the same month across two years.

        Args:
            month: Month to compare (1-12)
            year1: First year
            year2: Second year
            user_id: User ID
            account_id: Optional account ID

        Returns:
            Dictionary with monthly YoY comparison
        """
        summary1 = self.get_monthly_summary(year1, month, user_id, account_id)
        summary2 = self.get_monthly_summary(year2, month, user_id, account_id)

        spend_change = summary2['total_spend'] - summary1['total_spend']
        spend_change_pct = (spend_change / summary1['total_spend'] * 100) if summary1['total_spend'] > 0 else 0

        # Category comparison
        cat1_dict = {c['category']: c for c in summary1['category_breakdown']}
        cat2_dict = {c['category']: c for c in summary2['category_breakdown']}

        all_categories = set(cat1_dict.keys()) | set(cat2_dict.keys())

        category_comparison = []
        for cat in sorted(all_categories):
            amt1 = cat1_dict.get(cat, {}).get('amount', 0)
            amt2 = cat2_dict.get(cat, {}).get('amount', 0)
            change = amt2 - amt1
            change_pct = (change / amt1 * 100) if amt1 > 0 else 0

            category_comparison.append({
                'category': cat,
                'year1_amount': amt1,
                'year2_amount': amt2,
                'change': change,
                'change_pct': change_pct,
            })

        category_comparison.sort(key=lambda x: abs(x['change']), reverse=True)

        return {
            'month': month,
            'month_name': date(year1, month, 1).strftime('%B'),
            'year1': year1,
            'year2': year2,
            'year1_summary': summary1,
            'year2_summary': summary2,
            'spend_change': spend_change,
            'spend_change_pct': spend_change_pct,
            'category_comparison': category_comparison,
        }

    def get_spending_velocity(self, user_id: str,
                              months: int = 12,
                              account_id: str = None) -> Dict[str, Any]:
        """Calculate spending velocity (trend) over recent months.

        Args:
            user_id: User ID
            months: Number of months to analyze
            account_id: Optional account ID

        Returns:
            Dictionary with spending velocity data
        """
        now = datetime.now()
        monthly_data = []

        for i in range(months - 1, -1, -1):
            # Calculate the month (going backwards from current)
            year = now.year
            month = now.month - i
            while month <= 0:
                month += 12
                year -= 1

            summary = self.get_monthly_summary(year, month, user_id, account_id)
            monthly_data.append({
                'year': year,
                'month': month,
                'month_name': date(year, month, 1).strftime('%b %Y'),
                'total_spend': summary['total_spend'],
                'total_income': summary['total_income'],
                'net': summary['net'],
            })

        # Calculate trend (simple linear regression)
        if len(monthly_data) >= 2:
            spends = [m['total_spend'] for m in monthly_data]
            n = len(spends)
            x_mean = (n - 1) / 2
            y_mean = sum(spends) / n

            numerator = sum((i - x_mean) * (spends[i] - y_mean) for i in range(n))
            denominator = sum((i - x_mean) ** 2 for i in range(n))

            slope = numerator / denominator if denominator != 0 else 0
            trend_direction = 'increasing' if slope > 10 else ('decreasing' if slope < -10 else 'stable')
        else:
            slope = 0
            trend_direction = 'insufficient_data'

        avg_spend = sum(m['total_spend'] for m in monthly_data) / len(monthly_data) if monthly_data else 0
        avg_income = sum(m['total_income'] for m in monthly_data) / len(monthly_data) if monthly_data else 0

        return {
            'months_analyzed': months,
            'monthly_data': monthly_data,
            'avg_monthly_spend': avg_spend,
            'avg_monthly_income': avg_income,
            'avg_monthly_net': avg_income - avg_spend,
            'trend_slope': slope,
            'trend_direction': trend_direction,
        }
