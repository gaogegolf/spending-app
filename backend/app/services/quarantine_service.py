"""Quarantine service - business logic for managing quarantined transactions."""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.models.quarantined_transaction import (
    QuarantinedTransaction,
    QuarantineErrorType,
    QuarantineStatus,
)
from app.models.import_record import ImportRecord
from app.models.transaction import Transaction
from app.models.account import Account
from app.services.deduplication import DeduplicationService

logger = logging.getLogger(__name__)


class QuarantineService:
    """Service for managing quarantined transactions."""

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id
        self.dedup_service = DeduplicationService(db)

    def list_quarantined(
        self,
        import_id: Optional[str] = None,
        status: Optional[QuarantineStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[QuarantinedTransaction], int, int]:
        """List quarantined transactions for current user.

        Args:
            import_id: Filter by specific import
            status: Filter by status
            limit: Max items to return
            offset: Pagination offset

        Returns:
            Tuple of (items, total_count, pending_count)
        """
        query = self.db.query(QuarantinedTransaction).filter(
            QuarantinedTransaction.user_id == self.user_id
        )

        if import_id:
            query = query.filter(QuarantinedTransaction.import_id == import_id)

        if status:
            query = query.filter(QuarantinedTransaction.status == status)

        total = query.count()

        # Get pending count (for badge display)
        pending_count = self.db.query(QuarantinedTransaction).filter(
            QuarantinedTransaction.user_id == self.user_id,
            QuarantinedTransaction.status == QuarantineStatus.PENDING,
        ).count()

        items = query.order_by(QuarantinedTransaction.created_at.desc()).offset(offset).limit(limit).all()

        return items, total, pending_count

    def get_quarantined(self, quarantine_id: str) -> Optional[QuarantinedTransaction]:
        """Get a single quarantined transaction."""
        return self.db.query(QuarantinedTransaction).filter(
            QuarantinedTransaction.id == quarantine_id,
            QuarantinedTransaction.user_id == self.user_id,
        ).first()

    def update_quarantined(
        self,
        quarantine_id: str,
        updates: Dict[str, Any],
    ) -> Optional[QuarantinedTransaction]:
        """Update fields on a quarantined transaction.

        Args:
            quarantine_id: ID of quarantined item
            updates: Dict of field updates (date, amount, description, etc.)

        Returns:
            Updated quarantined transaction or None if not found
        """
        item = self.get_quarantined(quarantine_id)
        if not item:
            return None

        if item.status != QuarantineStatus.PENDING:
            raise ValueError("Cannot update resolved or discarded item")

        # Update raw_data with new values
        raw_data = dict(item.raw_data)
        for key, value in updates.items():
            if value is not None:
                raw_data[key] = value

        item.raw_data = raw_data
        self.db.commit()
        self.db.refresh(item)

        return item

    def retry_quarantined(self, quarantine_id: str) -> Tuple[QuarantinedTransaction, Optional[str]]:
        """Attempt to retry importing a quarantined transaction.

        Args:
            quarantine_id: ID of quarantined item

        Returns:
            Tuple of (quarantined_item, transaction_id if success)
        """
        item = self.get_quarantined(quarantine_id)
        if not item:
            raise ValueError("Quarantined item not found")

        if item.status != QuarantineStatus.PENDING:
            raise ValueError("Cannot retry resolved or discarded item")

        # Validate and transform the raw data
        try:
            txn_data = self._validate_and_transform(item.raw_data, item.account_id)
        except ValueError as e:
            # Update error and increment retry count
            item.error_message = str(e)
            item.retry_count += 1
            self.db.commit()
            return item, None

        # Check for duplicates
        if item.account_id:
            import_record = item.import_record
            duplicate_hashes = self.dedup_service.check_duplicates(
                account_id=item.account_id,
                file_hash=import_record.file_hash if import_record else None,
                transactions=[txn_data],
            )
            if duplicate_hashes:
                item.error_type = QuarantineErrorType.DUPLICATE
                item.error_message = "Transaction is a duplicate of existing record"
                item.retry_count += 1
                self.db.commit()
                return item, None

        # Create the transaction
        transaction = self._create_transaction(txn_data, item)

        # Mark as resolved
        item.status = QuarantineStatus.RESOLVED
        item.resolved_at = datetime.utcnow()

        # Update import record counts
        if item.import_record:
            item.import_record.transactions_imported += 1
            item.import_record.transactions_quarantined -= 1
            # Check if all quarantine items are resolved
            pending = self.db.query(QuarantinedTransaction).filter(
                QuarantinedTransaction.import_id == item.import_id,
                QuarantinedTransaction.status == QuarantineStatus.PENDING,
            ).count()
            item.import_record.quarantine_resolved = (pending == 0)

        self.db.commit()
        self.db.refresh(item)

        return item, transaction.id

    def discard_quarantined(self, quarantine_id: str) -> Optional[QuarantinedTransaction]:
        """Discard a quarantined transaction (won't be imported).

        Args:
            quarantine_id: ID of quarantined item

        Returns:
            Updated quarantined transaction or None if not found
        """
        item = self.get_quarantined(quarantine_id)
        if not item:
            return None

        if item.status != QuarantineStatus.PENDING:
            raise ValueError("Cannot discard resolved or already discarded item")

        item.status = QuarantineStatus.DISCARDED
        item.resolved_at = datetime.utcnow()

        # Update import record
        if item.import_record:
            item.import_record.transactions_quarantined -= 1
            pending = self.db.query(QuarantinedTransaction).filter(
                QuarantinedTransaction.import_id == item.import_id,
                QuarantinedTransaction.status == QuarantineStatus.PENDING,
            ).count()
            item.import_record.quarantine_resolved = (pending == 0)

        self.db.commit()
        self.db.refresh(item)

        return item

    def bulk_retry(self, ids: List[str]) -> List[Tuple[str, bool, Optional[str], Optional[str]]]:
        """Retry multiple quarantined items.

        Args:
            ids: List of quarantine IDs to retry

        Returns:
            List of (id, success, transaction_id, error_message) tuples
        """
        results = []
        for qid in ids:
            try:
                item, txn_id = self.retry_quarantined(qid)
                success = item.status == QuarantineStatus.RESOLVED
                results.append((qid, success, txn_id, None if success else item.error_message))
            except ValueError as e:
                results.append((qid, False, None, str(e)))
        return results

    def bulk_discard(self, ids: List[str]) -> List[Tuple[str, bool, Optional[str]]]:
        """Discard multiple quarantined items.

        Args:
            ids: List of quarantine IDs to discard

        Returns:
            List of (id, success, error_message) tuples
        """
        results = []
        for qid in ids:
            try:
                item = self.discard_quarantined(qid)
                results.append((qid, item is not None, None))
            except ValueError as e:
                results.append((qid, False, str(e)))
        return results

    def _validate_and_transform(
        self,
        raw_data: Dict[str, Any],
        account_id: Optional[str],
    ) -> Dict[str, Any]:
        """Validate and transform raw data into transaction format.

        Args:
            raw_data: Raw row data from quarantine
            account_id: Target account ID

        Returns:
            Validated transaction data dict

        Raises:
            ValueError: If validation fails
        """
        errors = []
        parsed_date = None
        amount_decimal = None

        # Validate date
        date_str = raw_data.get('date')
        if not date_str:
            errors.append("Missing date")
        else:
            # Try common formats
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%d/%m/%Y']:
                try:
                    parsed_date = datetime.strptime(str(date_str), fmt).date()
                    break
                except ValueError:
                    continue
            if not parsed_date:
                errors.append(f"Cannot parse date: {date_str}")

        # Validate amount
        amount = raw_data.get('amount')
        if amount is None:
            errors.append("Missing amount")
        else:
            try:
                amount_decimal = Decimal(str(amount))
            except (InvalidOperation, ValueError):
                errors.append(f"Invalid amount: {amount}")

        # Validate description
        description = raw_data.get('description_raw') or raw_data.get('description')
        if not description:
            errors.append("Missing description")

        if errors:
            raise ValueError("; ".join(errors))

        # Return transformed data
        return {
            **raw_data,
            'date': str(parsed_date),
            'amount': float(amount_decimal),
        }

    def _create_transaction(
        self,
        txn_data: Dict[str, Any],
        quarantine_item: QuarantinedTransaction,
    ) -> Transaction:
        """Create a transaction from validated data.

        Args:
            txn_data: Validated transaction data
            quarantine_item: Source quarantine item

        Returns:
            Created Transaction
        """
        from app.models.transaction import Transaction, TransactionType

        # Determine transaction type
        amount = float(txn_data.get('amount', 0))
        txn_type = TransactionType.EXPENSE if amount > 0 else TransactionType.INCOME

        transaction = Transaction(
            account_id=quarantine_item.account_id,
            import_id=quarantine_item.import_id,
            date=txn_data.get('date'),
            amount=abs(amount),
            description_raw=txn_data.get('description_raw', txn_data.get('description', '')),
            merchant_normalized=txn_data.get('merchant_normalized', ''),
            transaction_type=txn_type,
            category=txn_data.get('category', 'Uncategorized'),
            is_spend=amount > 0,
            is_income=amount < 0,
            needs_review=True,
        )

        self.db.add(transaction)
        return transaction


def create_quarantine_item(
    db: Session,
    import_record: ImportRecord,
    raw_data: Dict[str, Any],
    error_type: QuarantineErrorType,
    error_message: str,
    error_field: Optional[str] = None,
) -> QuarantinedTransaction:
    """Helper to create a quarantine item during import.

    Args:
        db: Database session
        import_record: Parent import record
        raw_data: Original row data
        error_type: Type of error
        error_message: Human-readable error
        error_field: Field that caused the error

    Returns:
        Created QuarantinedTransaction
    """
    item = QuarantinedTransaction(
        import_id=import_record.id,
        account_id=import_record.account_id,
        user_id=import_record.user_id or (import_record.account.user_id if import_record.account else None),
        raw_data=raw_data,
        error_type=error_type,
        error_message=error_message,
        error_field=error_field,
    )
    db.add(item)
    return item
