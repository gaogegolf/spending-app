#!/usr/bin/env python3
"""Backfill bank balance snapshots from existing PDF statements.

This script re-parses existing bank statement PDFs to extract balance information
and creates HoldingsSnapshot records for net worth tracking.

Usage:
    cd backend && python -m scripts.backfill_bank_balances
"""

import os
import sys
import hashlib
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models.account import Account, AccountType
from app.models.holdings_snapshot import HoldingsSnapshot
from app.models.import_record import ImportRecord
from app.services.file_parser.pdf_parser import PDFParser


def compute_file_hash(file_path: str) -> str:
    """Compute SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def find_or_create_account(
    db: Session,
    institution: str,
    account_type: AccountType,
    last4: str,
) -> Account:
    """Find existing account or create new one."""
    account = db.query(Account).filter(
        Account.institution == institution,
        Account.account_type == account_type,
        Account.account_number_last4 == last4,
    ).first()

    if account:
        return account

    # Create new account
    type_labels = {
        AccountType.CHECKING: 'Checking',
        AccountType.SAVINGS: 'Savings',
    }
    type_label = type_labels.get(account_type, 'Account')
    name = f"{institution} {type_label}"

    account = Account(
        name=name,
        institution=institution,
        account_type=account_type,
        account_number_last4=last4,
        currency='USD',
        is_active=True,
    )
    db.add(account)
    db.flush()
    print(f"  Created new account: {name} (***{last4})")

    return account


def process_bank_pdf(db: Session, pdf_path: str, institution: str) -> int:
    """Parse a bank PDF and create balance snapshots.

    Returns number of snapshots created.
    """
    file_hash = compute_file_hash(pdf_path)

    # Check if we already have snapshots for this file
    existing = db.query(HoldingsSnapshot).filter(
        HoldingsSnapshot.source_file_hash == file_hash
    ).first()

    if existing:
        return 0  # Already processed

    # Parse the PDF
    parser = PDFParser(pdf_path)
    result = parser.parse()

    if not result.success:
        print(f"  Failed to parse: {result.errors}")
        return 0

    balances = result.metadata.get('balances', {})
    statement_date_str = result.metadata.get('statement_date')

    if not balances or not statement_date_str:
        print(f"  No balance data found")
        return 0

    from datetime import date
    stmt_date = date.fromisoformat(statement_date_str)

    # Map account type strings to AccountType
    type_map = {
        'spending': AccountType.CHECKING,
        'checking': AccountType.CHECKING,
        'savings': AccountType.SAVINGS,
    }

    snapshots_created = 0

    for account_type_str, balance_info in balances.items():
        account_type = type_map.get(account_type_str.lower(), AccountType.OTHER)
        last4 = balance_info.get('last4', '')
        ending = Decimal(str(balance_info.get('ending', 0)))

        if ending == 0:
            continue

        # Find or create account
        account = find_or_create_account(db, institution, account_type, last4)

        # Check for existing snapshot for this account + date
        existing_snapshot = db.query(HoldingsSnapshot).filter(
            HoldingsSnapshot.account_id == account.id,
            HoldingsSnapshot.statement_date == stmt_date,
        ).first()

        if existing_snapshot:
            # Update existing
            existing_snapshot.total_value = ending
            existing_snapshot.total_cash = ending
            existing_snapshot.source_file_hash = file_hash
            print(f"  Updated: {account.name} {stmt_date} = ${ending:,.2f}")
        else:
            # Create new snapshot
            snapshot = HoldingsSnapshot(
                account_id=account.id,
                statement_date=stmt_date,
                total_value=ending,
                total_cash=ending,
                total_securities=Decimal('0'),
                calculated_total=ending,
                is_reconciled=True,
                reconciliation_diff=Decimal('0'),
                source_file_hash=file_hash,
                base_currency='USD',
                currency='USD',
            )
            db.add(snapshot)
            print(f"  Created: {account.name} {stmt_date} = ${ending:,.2f}")
            snapshots_created += 1

    return snapshots_created


def main():
    """Main entry point."""
    print("=" * 60)
    print("Bank Balance Backfill Script")
    print("=" * 60)

    # Bank directories
    bank_dirs = {
        'Ally Bank': '/Users/I858764/Documents/Spending/Bank/Ge Ally Bank',
        'Chase': '/Users/I858764/Documents/Spending/Bank/Ge Chase Bank',
    }

    db = SessionLocal()

    try:
        total_created = 0
        total_files = 0

        for institution, dir_path in bank_dirs.items():
            print(f"\n{institution}: {dir_path}")
            print("-" * 50)

            if not os.path.exists(dir_path):
                print(f"  Directory not found, skipping")
                continue

            pdf_files = sorted([f for f in os.listdir(dir_path) if f.endswith('.pdf')])
            print(f"  Found {len(pdf_files)} PDF files")

            for pdf_file in pdf_files:
                pdf_path = os.path.join(dir_path, pdf_file)
                print(f"\n  Processing: {pdf_file}")

                total_files += 1
                created = process_bank_pdf(db, pdf_path, institution)
                total_created += created

        db.commit()

        print("\n" + "=" * 60)
        print(f"Summary:")
        print(f"  Files processed: {total_files}")
        print(f"  Snapshots created: {total_created}")
        print("=" * 60)

        # Show final account summary
        print("\nAccount balances in database:")
        print("-" * 50)

        from sqlalchemy import func
        accounts = db.query(Account).filter(
            Account.account_type.in_([AccountType.CHECKING, AccountType.SAVINGS])
        ).all()

        for account in accounts:
            latest = db.query(HoldingsSnapshot).filter(
                HoldingsSnapshot.account_id == account.id
            ).order_by(HoldingsSnapshot.statement_date.desc()).first()

            if latest:
                print(f"  {account.name}: ${latest.total_value:,.2f} ({latest.statement_date})")

    finally:
        db.close()


if __name__ == "__main__":
    main()
