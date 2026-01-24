"""Service for detecting recurring transactions (subscriptions)."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from collections import defaultdict
import statistics

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.transaction import Transaction, TransactionType
from app.models.recurring_transaction import RecurringTransaction, RecurringFrequency


class RecurringDetectionService:
    """Service for detecting recurring transactions from transaction history."""

    # Frequency detection thresholds (in days)
    FREQUENCY_RANGES = {
        RecurringFrequency.WEEKLY: (5, 9),       # 7 days ± 2
        RecurringFrequency.BIWEEKLY: (12, 18),   # 14 days ± 2-4
        RecurringFrequency.MONTHLY: (26, 35),    # 30 days ± 4-5
        RecurringFrequency.QUARTERLY: (80, 100), # 90 days ± 10
        RecurringFrequency.YEARLY: (350, 380),   # 365 days ± 15
    }

    # Minimum transactions required for detection
    MIN_TRANSACTIONS = 3

    # Amount tolerance for consistency check (percentage)
    AMOUNT_TOLERANCE_PERCENT = 5.0

    # Minimum confidence score to consider as candidate
    MIN_CONFIDENCE = 0.7

    def __init__(self, db: Session):
        self.db = db

    def detect_candidates(
        self,
        user_id: str = "default_user",
        min_transactions: int = None,
        min_confidence: float = None
    ) -> list[dict]:
        """
        Detect recurring transaction candidates from transaction history.

        Algorithm:
        1. Group transactions by normalized merchant name
        2. For each merchant with 3+ transactions:
           - Calculate date intervals between transactions
           - Check amount consistency (±5%)
           - Detect frequency pattern
        3. Score confidence based on consistency
        4. Return candidates with confidence > threshold

        Returns:
            List of RecurringCandidate dictionaries
        """
        min_transactions = min_transactions or self.MIN_TRANSACTIONS
        min_confidence = min_confidence or self.MIN_CONFIDENCE

        # Get all expense transactions grouped by merchant
        transactions = (
            self.db.query(Transaction)
            .filter(
                Transaction.transaction_type == TransactionType.EXPENSE,
                Transaction.merchant_normalized.isnot(None),
                Transaction.merchant_normalized != "",
            )
            .order_by(Transaction.merchant_normalized, Transaction.date)
            .all()
        )

        # Group by merchant
        merchant_transactions = defaultdict(list)
        for txn in transactions:
            merchant_transactions[txn.merchant_normalized].append(txn)

        candidates = []

        for merchant, txns in merchant_transactions.items():
            if len(txns) < min_transactions:
                continue

            candidate = self._analyze_merchant_transactions(merchant, txns)
            if candidate and candidate["confidence"] >= min_confidence:
                candidates.append(candidate)

        # Sort by confidence descending
        candidates.sort(key=lambda x: x["confidence"], reverse=True)

        return candidates

    def _analyze_merchant_transactions(
        self,
        merchant: str,
        transactions: list[Transaction]
    ) -> Optional[dict]:
        """Analyze transactions for a single merchant to detect patterns."""

        if len(transactions) < self.MIN_TRANSACTIONS:
            return None

        # Sort by date
        transactions = sorted(transactions, key=lambda t: t.date)

        # Calculate intervals between transactions
        intervals = []
        for i in range(1, len(transactions)):
            days = (transactions[i].date - transactions[i - 1].date).days
            if days > 0:  # Ignore same-day transactions
                intervals.append(days)

        if len(intervals) < 2:
            return None

        # Calculate amount statistics
        amounts = [float(t.amount) for t in transactions]
        avg_amount = statistics.mean(amounts)
        if avg_amount == 0:
            return None

        amount_stdev = statistics.stdev(amounts) if len(amounts) > 1 else 0
        amount_variance_pct = (amount_stdev / avg_amount) * 100

        # Detect frequency pattern
        avg_interval = statistics.mean(intervals)
        interval_stdev = statistics.stdev(intervals) if len(intervals) > 1 else 0

        frequency = self._detect_frequency(avg_interval)
        if not frequency:
            return None

        # Calculate confidence score
        confidence = self._calculate_confidence(
            transaction_count=len(transactions),
            amount_variance_pct=amount_variance_pct,
            interval_stdev=interval_stdev,
            avg_interval=avg_interval,
            frequency=frequency
        )

        # Calculate next expected date
        last_date = transactions[-1].date
        expected_interval = self._get_expected_interval(frequency)
        next_expected = last_date + timedelta(days=expected_interval)

        return {
            "merchant_normalized": merchant,
            "expected_amount": Decimal(str(round(avg_amount, 2))),
            "frequency": frequency,
            "confidence": Decimal(str(round(confidence, 2))),
            "transaction_count": len(transactions),
            "avg_interval_days": round(avg_interval, 1),
            "amount_variance": Decimal(str(round(amount_variance_pct, 2))),
            "first_date": transactions[0].date,
            "last_date": last_date,
            "next_expected_date": next_expected,
            "sample_transaction_ids": [t.id for t in transactions[-5:]],  # Last 5 transactions
            "last_transaction_id": transactions[-1].id,
        }

    def _detect_frequency(self, avg_interval: float) -> Optional[RecurringFrequency]:
        """Detect frequency based on average interval between transactions."""

        for frequency, (min_days, max_days) in self.FREQUENCY_RANGES.items():
            if min_days <= avg_interval <= max_days:
                return frequency

        return None

    def _get_expected_interval(self, frequency: RecurringFrequency) -> int:
        """Get expected interval in days for a frequency."""

        intervals = {
            RecurringFrequency.WEEKLY: 7,
            RecurringFrequency.BIWEEKLY: 14,
            RecurringFrequency.MONTHLY: 30,
            RecurringFrequency.QUARTERLY: 90,
            RecurringFrequency.YEARLY: 365,
        }
        return intervals.get(frequency, 30)

    def _calculate_confidence(
        self,
        transaction_count: int,
        amount_variance_pct: float,
        interval_stdev: float,
        avg_interval: float,
        frequency: RecurringFrequency
    ) -> float:
        """
        Calculate confidence score for a detected pattern.

        Factors:
        - Transaction count: More transactions = higher confidence
        - Amount consistency: Lower variance = higher confidence
        - Interval consistency: Lower standard deviation = higher confidence
        """

        # Transaction count factor (0.0 to 0.3)
        # 3 transactions = 0.15, 6+ = 0.3
        count_score = min(0.3, (transaction_count - 2) * 0.05)

        # Amount consistency factor (0.0 to 0.4)
        # 0% variance = 0.4, >10% variance = 0
        amount_score = max(0, 0.4 - (amount_variance_pct / 25))

        # Interval consistency factor (0.0 to 0.3)
        # Perfect consistency = 0.3, high variance = 0
        expected_interval = self._get_expected_interval(frequency)
        interval_variance_ratio = interval_stdev / expected_interval if expected_interval > 0 else 1
        interval_score = max(0, 0.3 - (interval_variance_ratio * 0.6))

        total_confidence = count_score + amount_score + interval_score

        return min(1.0, max(0.0, total_confidence))

    def create_from_candidate(
        self,
        candidate: dict,
        user_id: str = "default_user"
    ) -> RecurringTransaction:
        """Create a RecurringTransaction from a detected candidate."""

        recurring = RecurringTransaction(
            user_id=user_id,
            merchant_normalized=candidate["merchant_normalized"],
            expected_amount=candidate["expected_amount"],
            amount_tolerance=Decimal("5.0"),
            frequency=candidate["frequency"],
            next_expected_date=candidate.get("next_expected_date"),
            last_transaction_id=candidate.get("last_transaction_id"),
            is_active=True,
            is_auto_detected=True,
            confidence=candidate["confidence"],
        )

        self.db.add(recurring)
        self.db.commit()
        self.db.refresh(recurring)

        return recurring

    def get_upcoming(
        self,
        user_id: str = "default_user",
        days_ahead: int = 30
    ) -> list[dict]:
        """Get upcoming recurring payments within the specified number of days."""

        today = date.today()
        end_date = today + timedelta(days=days_ahead)

        recurring = (
            self.db.query(RecurringTransaction)
            .filter(
                RecurringTransaction.user_id == user_id,
                RecurringTransaction.is_active == True,
                RecurringTransaction.next_expected_date.isnot(None),
                RecurringTransaction.next_expected_date >= today,
                RecurringTransaction.next_expected_date <= end_date,
            )
            .order_by(RecurringTransaction.next_expected_date)
            .all()
        )

        upcoming = []
        for r in recurring:
            days_until = (r.next_expected_date - today).days
            upcoming.append({
                "id": r.id,
                "merchant_normalized": r.merchant_normalized,
                "expected_amount": r.expected_amount,
                "next_expected_date": r.next_expected_date,
                "days_until": days_until,
                "frequency": r.frequency,
                "category": r.category,
            })

        return upcoming

    def get_summary(self, user_id: str = "default_user") -> dict:
        """Get summary statistics for recurring transactions."""

        recurring = (
            self.db.query(RecurringTransaction)
            .filter(
                RecurringTransaction.user_id == user_id,
                RecurringTransaction.is_active == True,
            )
            .all()
        )

        total_active = len(recurring)
        total_monthly_cost = Decimal("0")
        total_yearly_cost = Decimal("0")

        category_totals = defaultdict(Decimal)
        frequency_totals = defaultdict(int)

        for r in recurring:
            monthly = self._calculate_monthly_cost(r.expected_amount, r.frequency)
            yearly = monthly * 12

            total_monthly_cost += monthly
            total_yearly_cost += yearly

            category = r.category or "Uncategorized"
            category_totals[category] += monthly

            frequency_totals[r.frequency.value] += 1

        by_category = [
            {"category": cat, "monthly_cost": float(cost)}
            for cat, cost in sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
        ]

        by_frequency = [
            {"frequency": freq, "count": count}
            for freq, count in sorted(frequency_totals.items())
        ]

        return {
            "total_active": total_active,
            "total_monthly_cost": total_monthly_cost,
            "total_yearly_cost": total_yearly_cost,
            "by_category": by_category,
            "by_frequency": by_frequency,
        }

    def _calculate_monthly_cost(
        self,
        amount: Decimal,
        frequency: RecurringFrequency
    ) -> Decimal:
        """Calculate monthly cost for a recurring payment."""

        multipliers = {
            RecurringFrequency.WEEKLY: Decimal("4.33"),      # 52 weeks / 12 months
            RecurringFrequency.BIWEEKLY: Decimal("2.17"),   # 26 payments / 12 months
            RecurringFrequency.MONTHLY: Decimal("1"),
            RecurringFrequency.QUARTERLY: Decimal("0.33"),  # 4 payments / 12 months
            RecurringFrequency.YEARLY: Decimal("0.083"),    # 1 payment / 12 months
        }

        return amount * multipliers.get(frequency, Decimal("1"))

    def update_next_expected_date(
        self,
        recurring_id: str,
        transaction_date: date
    ) -> Optional[RecurringTransaction]:
        """Update next expected date after a matching transaction is found."""

        recurring = self.db.query(RecurringTransaction).filter(
            RecurringTransaction.id == recurring_id
        ).first()

        if not recurring:
            return None

        interval = self._get_expected_interval(recurring.frequency)
        recurring.next_expected_date = transaction_date + timedelta(days=interval)

        self.db.commit()
        self.db.refresh(recurring)

        return recurring
