"""Transaction deduplication service using hash-based detection.

Deduplication Strategy:
- Uses file_hash (SHA256 of file content) + row_index (position in file) to identify each transaction
- This ensures that:
  1. Two transactions with same date/amount/description from different files are NOT duplicates
  2. Re-uploading the same file will correctly identify all transactions as duplicates
- The row_index is added during parsing (CSV/PDF parsers)
- The file_hash is calculated during upload and stored in ImportRecord
"""

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

    def generate_hash(self, account_id: str, file_hash: str, transaction_data: Dict[str, Any]) -> str:
        """Generate a deterministic hash for transaction deduplication.

        The hash is based on:
        - Account ID (to scope duplicates per account)
        - File hash (SHA256 of the uploaded file)
        - Row index (position of transaction within the file)

        This ensures that:
        - Same file re-uploaded → same hash → detected as duplicate
        - Different files with similar transactions → different hash → NOT duplicates

        Args:
            account_id: Account ID
            file_hash: SHA256 hash of the source file
            transaction_data: Dict containing row_index from parser

        Returns:
            SHA256 hash string (64 characters)
        """
        account_id = str(account_id)
        row_index = transaction_data.get('row_index', 0)

        # Combine components: account_id + file_hash + row_index
        hash_input = f"{account_id}|{file_hash}|{row_index}"

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
        file_hash: str,
        transactions: List[Dict[str, Any]]
    ) -> Set[str]:
        """Check which transactions already exist in the database.

        Args:
            account_id: Account ID
            file_hash: SHA256 hash of the source file
            transactions: List of transaction dictionaries

        Returns:
            Set of hashes that already exist in database
        """
        from app.models.transaction import Transaction

        # Generate hashes for all transactions
        hashes = {
            self.generate_hash(account_id, file_hash, txn)
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
        file_hash: str,
        transactions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter out transactions that already exist in database.

        Args:
            account_id: Account ID
            file_hash: SHA256 hash of the source file
            transactions: List of transaction dictionaries

        Returns:
            List of new (non-duplicate) transactions
        """
        duplicate_hashes = self.check_duplicates(account_id, file_hash, transactions)

        # Filter out duplicates
        new_transactions = []
        for txn in transactions:
            txn_hash = self.generate_hash(account_id, file_hash, txn)
            if txn_hash not in duplicate_hashes:
                new_transactions.append(txn)

        return new_transactions
