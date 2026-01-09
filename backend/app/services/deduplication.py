"""Transaction deduplication service using hash-based detection."""

import hashlib
import re
from typing import Dict, Any, Optional, List, Set
from datetime import datetime, date
from sqlalchemy.orm import Session


class DeduplicationService:
    """Service for detecting and preventing duplicate transactions."""

    def __init__(self, db: Session):
        """Initialize deduplication service.

        Args:
            db: Database session
        """
        self.db = db

    def generate_hash(self, account_id: str, transaction_data: Dict[str, Any]) -> str:
        """Generate a deterministic hash for transaction deduplication.

        The hash is based on:
        - Account ID
        - Transaction date
        - Amount (rounded to 2 decimals)
        - Normalized description

        Args:
            account_id: Account ID
            transaction_data: Dict containing date, amount, description_raw

        Returns:
            SHA256 hash string (64 characters)
        """
        # Extract components
        account_id = str(account_id)

        # Handle date (could be string or date object)
        txn_date = transaction_data.get('date')
        if isinstance(txn_date, str):
            try:
                txn_date = datetime.fromisoformat(txn_date).date()
            except:
                txn_date = date.today()
        elif isinstance(txn_date, datetime):
            txn_date = txn_date.date()
        elif not isinstance(txn_date, date):
            txn_date = date.today()

        # Format date consistently
        date_str = txn_date.isoformat()

        # Round amount to 2 decimals
        amount = float(transaction_data.get('amount', 0))
        amount_str = f"{amount:.2f}"

        # Normalize description
        description = transaction_data.get('description_raw', '')
        normalized_desc = DeduplicationService._normalize_description(description)

        # Combine components
        hash_input = f"{account_id}|{date_str}|{amount_str}|{normalized_desc}"

        # Generate SHA256 hash
        return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

    @staticmethod
    def _normalize_description(description: str) -> str:
        """Normalize description for consistent hashing.

        Normalization steps:
        - Convert to lowercase
        - Remove extra whitespace
        - Remove special characters that might vary
        - Trim

        Args:
            description: Raw transaction description

        Returns:
            Normalized description
        """
        # Convert to lowercase
        normalized = description.lower()

        # Remove multiple spaces
        normalized = ' '.join(normalized.split())

        # Remove special characters that might vary (but keep basic punctuation)
        normalized = re.sub(r'[*#\s]+', ' ', normalized)

        # Trim
        normalized = normalized.strip()

        return normalized

    @staticmethod
    def is_likely_duplicate(txn1: Dict[str, Any], txn2: Dict[str, Any],
                           date_tolerance_days: int = 3) -> bool:
        """Check if two transactions are likely duplicates.

        Args:
            txn1: First transaction
            txn2: Second transaction
            date_tolerance_days: Number of days within which transactions are considered

        Returns:
            True if transactions are likely duplicates
        """
        # Check if amounts match
        amount1 = float(txn1.get('amount', 0))
        amount2 = float(txn2.get('amount', 0))

        if abs(amount1 - amount2) > 0.01:  # Allow 1 cent difference
            return False

        # Check if dates are within tolerance
        date1 = txn1.get('date')
        date2 = txn2.get('date')

        if isinstance(date1, str):
            date1 = datetime.fromisoformat(date1).date()
        if isinstance(date2, str):
            date2 = datetime.fromisoformat(date2).date()

        date_diff = abs((date1 - date2).days)
        if date_diff > date_tolerance_days:
            return False

        # Check if descriptions are similar
        desc1 = DeduplicationService._normalize_description(txn1.get('description_raw', ''))
        desc2 = DeduplicationService._normalize_description(txn2.get('description_raw', ''))

        # Simple similarity check - exact match after normalization
        return desc1 == desc2

    def check_duplicates(
        self,
        account_id: str,
        transactions: List[Dict[str, Any]]
    ) -> Set[str]:
        """Check which transactions already exist in the database.

        Args:
            account_id: Account ID
            transactions: List of transaction dictionaries

        Returns:
            Set of hashes that already exist in database
        """
        from app.models.transaction import Transaction

        # Generate hashes for all transactions
        hashes = {
            self.generate_hash(account_id, txn)
            for txn in transactions
        }

        # Query database for existing hashes
        existing = self.db.query(Transaction.hash_dedup_key).filter(
            Transaction.account_id == account_id,
            Transaction.hash_dedup_key.in_(hashes)
        ).all()

        return {row[0] for row in existing}

    def filter_duplicates(
        self,
        account_id: str,
        transactions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter out transactions that already exist in database.

        Args:
            account_id: Account ID
            transactions: List of transaction dictionaries

        Returns:
            List of new (non-duplicate) transactions
        """
        duplicate_hashes = self.check_duplicates(account_id, transactions)

        # Filter out duplicates
        new_transactions = []
        for txn in transactions:
            txn_hash = self.generate_hash(account_id, txn)
            if txn_hash not in duplicate_hashes:
                new_transactions.append(txn)

        return new_transactions
