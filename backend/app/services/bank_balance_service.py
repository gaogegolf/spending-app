"""Bank balance service for creating balance snapshots from bank statements."""

from datetime import date
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.account import Account, AccountType
from app.models.holdings_snapshot import HoldingsSnapshot
from app.models.import_record import ImportRecord


class BankBalanceService:
    """Service to create HoldingsSnapshot records from parsed bank balances.

    Reuses HoldingsSnapshot model for bank account balances:
    - total_value = ending_balance
    - total_cash = ending_balance
    - total_securities = 0
    - positions = [] (empty)
    - is_reconciled = True
    """

    def __init__(self, db: Session):
        self.db = db

    def create_balance_snapshots(
        self,
        import_record: ImportRecord,
        balances: Dict[str, Dict[str, Any]],
        statement_date: Optional[str],
        institution: str,
    ) -> List[HoldingsSnapshot]:
        """Create HoldingsSnapshot records from parsed bank balances.

        Args:
            import_record: The import record for the statement
            balances: Dict from parser, e.g. {'checking': {'last4': '0322', 'ending': 5754.30}, ...}
            statement_date: ISO format date string (YYYY-MM-DD) or None
            institution: Bank name ('Ally Bank', 'Chase')

        Returns:
            List of created HoldingsSnapshot objects (not yet committed)
        """
        if not balances or not statement_date:
            return []

        snapshots = []
        stmt_date = date.fromisoformat(statement_date)

        for account_type_str, balance_info in balances.items():
            # Map account type string to AccountType
            account_type = self._map_account_type(account_type_str)
            last4 = balance_info.get('last4', '')
            ending_balance = Decimal(str(balance_info.get('ending', 0)))

            # Skip zero balances
            if ending_balance == 0:
                continue

            # Find or create account
            account = self._find_or_create_account(
                institution=institution,
                account_type=account_type,
                last4=last4,
            )

            # Check for duplicate snapshot (same account + date)
            existing = self.db.query(HoldingsSnapshot).filter(
                HoldingsSnapshot.account_id == account.id,
                HoldingsSnapshot.statement_date == stmt_date,
            ).first()

            if existing:
                # Update existing snapshot
                existing.total_value = ending_balance
                existing.total_cash = ending_balance
                existing.total_securities = Decimal('0')
                existing.calculated_total = ending_balance
                existing.is_reconciled = True
                existing.reconciliation_diff = Decimal('0')
                existing.import_id = import_record.id
                existing.source_file_hash = import_record.file_hash
                snapshots.append(existing)
            else:
                # Create new snapshot
                snapshot = HoldingsSnapshot(
                    account_id=account.id,
                    import_id=import_record.id,
                    statement_date=stmt_date,
                    total_value=ending_balance,
                    total_cash=ending_balance,
                    total_securities=Decimal('0'),
                    calculated_total=ending_balance,
                    is_reconciled=True,
                    reconciliation_diff=Decimal('0'),
                    source_file_hash=import_record.file_hash,
                    base_currency='USD',
                    currency='USD',
                )
                self.db.add(snapshot)
                snapshots.append(snapshot)

        return snapshots

    def _map_account_type(self, account_type_str: str) -> AccountType:
        """Map account type string from parser to AccountType enum."""
        mapping = {
            'spending': AccountType.CHECKING,
            'checking': AccountType.CHECKING,
            'savings': AccountType.SAVINGS,
        }
        return mapping.get(account_type_str.lower(), AccountType.OTHER)

    def _find_or_create_account(
        self,
        institution: str,
        account_type: AccountType,
        last4: str,
    ) -> Account:
        """Find existing account or create new one.

        Matches on institution + account_type + last4.
        """
        # Try to find existing account
        account = self.db.query(Account).filter(
            Account.institution == institution,
            Account.account_type == account_type,
            Account.account_number_last4 == last4,
        ).first()

        if account:
            return account

        # Create new account
        name = self._generate_account_name(institution, account_type)
        account = Account(
            name=name,
            institution=institution,
            account_type=account_type,
            account_number_last4=last4,
            currency='USD',
            is_active=True,
        )
        self.db.add(account)
        self.db.flush()  # Get ID assigned

        return account

    def _generate_account_name(self, institution: str, account_type: AccountType) -> str:
        """Generate a user-friendly account name."""
        type_labels = {
            AccountType.CHECKING: 'Checking',
            AccountType.SAVINGS: 'Savings',
        }
        type_label = type_labels.get(account_type, 'Account')
        return f"{institution} {type_label}"
