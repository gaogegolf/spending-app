"""Shared account number hashing utility."""

import hashlib


def compute_account_hash(raw_account_number: str) -> str:
    """Compute SHA256 hash of normalized account number.

    Strips dashes, spaces, and uppercases before hashing.
    """
    normalized = raw_account_number.replace("-", "").replace(" ", "").strip().upper()
    return hashlib.sha256(normalized.encode()).hexdigest()
