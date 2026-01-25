"""Brokerage import service - handles brokerage statement import workflow."""

import os
import hashlib
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import func
from fastapi import UploadFile

from app.models.import_record import ImportRecord, SourceType, ImportStatus
from app.models.account import Account, AccountType
from app.models.holdings_snapshot import HoldingsSnapshot
from app.models.position import Position, PositionType, AssetClass
from app.models.fx_rate import FxRate
from app.services.file_parser.brokerage_parser import (
    BrokerageParseResult,
    PositionData,
    detect_brokerage_provider,
)
from app.services.file_parser.fidelity_brokerage_parser import FidelityBrokerageParser
from app.services.file_parser.schwab_brokerage_parser import SchwabBrokerageParser
from app.services.file_parser.ibkr_brokerage_parser import IBKRBrokerageParser
from app.services.file_parser.vanguard_brokerage_parser import VanguardBrokerageParser
from app.config import settings

logger = logging.getLogger(__name__)


class BrokerageImportService:
    """Service to orchestrate brokerage statement import."""

    def __init__(self, db: Session, user_id: str = None):
        """Initialize brokerage import service.

        Args:
            db: Database session
            user_id: User ID for user-specific operations
        """
        self.db = db
        self.user_id = user_id
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def upload(
        self,
        file: UploadFile,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Upload a brokerage PDF and detect provider.

        Args:
            file: Uploaded PDF file
            account_id: Optional account ID (if known)

        Returns:
            Dict with import_id, detected provider, and account type
        """
        filename = file.filename
        if not filename.lower().endswith('.pdf'):
            raise ValueError("Only PDF files are supported for brokerage statements")

        # Read file content
        file_content = await file.read()
        file_hash = hashlib.sha256(file_content).hexdigest()
        await file.seek(0)

        # Save file temporarily
        temp_path = self.upload_dir / f"brokerage_{file_hash[:16]}_{filename}"
        with open(temp_path, "wb") as f:
            f.write(file_content)

        # Detect provider from PDF
        import pdfplumber
        with pdfplumber.open(temp_path) as pdf:
            text_parts = []
            for page in pdf.pages[:3]:  # Check first 3 pages
                text_parts.append(page.extract_text() or "")
            full_text = "\n".join(text_parts)

        provider = detect_brokerage_provider(full_text)
        if not provider:
            os.remove(temp_path)
            raise ValueError(
                "Could not detect brokerage provider. "
                "Currently supported: Fidelity, Schwab, Interactive Brokers (IBKR), Vanguard"
            )

        # Create import record
        import_record = ImportRecord(
            account_id=account_id or "pending",  # Will be updated on commit
            source_type=SourceType.PDF,
            filename=filename,
            file_size_bytes=len(file_content),
            file_hash=file_hash,
            status=ImportStatus.PENDING,
            import_metadata={
                "type": "brokerage",
                "provider": provider,
                "temp_path": str(temp_path),
            }
        )

        self.db.add(import_record)
        self.db.commit()
        self.db.refresh(import_record)

        return {
            "import_id": import_record.id,
            "provider": provider,
            "filename": filename,
            "file_hash": file_hash,
            "status": "uploaded",
        }

    async def parse(self, import_id: str) -> Dict[str, Any]:
        """Parse brokerage statement and return preview.

        Args:
            import_id: Import record ID

        Returns:
            Dict with parsed holdings preview. For multi-account statements,
            returns an "accounts" array with multiple results.
        """
        import_record = self.db.query(ImportRecord).filter(
            ImportRecord.id == import_id
        ).first()

        if not import_record:
            raise ValueError(f"Import record {import_id} not found")

        metadata = import_record.import_metadata or {}
        if metadata.get("type") != "brokerage":
            raise ValueError("This is not a brokerage import")

        temp_path = metadata.get("temp_path")
        if not temp_path or not os.path.exists(temp_path):
            raise FileNotFoundError("Uploaded file not found")

        provider = metadata.get("provider")
        parser = self._get_parser(provider, temp_path)

        # Check for multi-account statement (IBKR or Fidelity)
        if hasattr(parser, 'is_multi_account_statement'):
            if parser.is_multi_account_statement():
                return await self._parse_multi_account(import_record, parser, metadata)

        # Single account parsing
        result = parser.parse()

        if not result.success:
            import_record.status = ImportStatus.FAILED
            import_record.error_message = "; ".join(result.errors)
            self.db.commit()
            raise ValueError(f"Failed to parse statement: {'; '.join(result.errors)}")

        # Store parse result in metadata for commit
        metadata["parse_result"] = self._result_to_dict(result)
        metadata["is_multi_account"] = False
        import_record.import_metadata = metadata
        flag_modified(import_record, "import_metadata")  # Ensure SQLAlchemy detects JSON change
        import_record.status = ImportStatus.PROCESSING
        self.db.commit()

        return self._format_single_result(import_id, result)

    async def _parse_multi_account(
        self,
        import_record: ImportRecord,
        parser: Any,  # Can be IBKRBrokerageParser or FidelityBrokerageParser
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse multi-account statement (IBKR or Fidelity).

        Args:
            import_record: The import record
            parser: Parser instance with parse_all() method
            metadata: Import metadata

        Returns:
            Dict with multiple account results
        """
        results = parser.parse_all()

        if not results:
            import_record.status = ImportStatus.FAILED
            import_record.error_message = "No accounts found in statement"
            self.db.commit()
            raise ValueError("No accounts found in multi-account statement")

        # Check if any failed
        failed = [r for r in results if not r.success]
        if len(failed) == len(results):
            import_record.status = ImportStatus.FAILED
            import_record.error_message = "; ".join(failed[0].errors)
            self.db.commit()
            raise ValueError(f"Failed to parse all accounts: {'; '.join(failed[0].errors)}")

        # Store all parse results in metadata
        metadata["is_multi_account"] = True
        metadata["account_count"] = len(results)
        metadata["parse_results"] = [self._result_to_dict(r) for r in results]
        import_record.import_metadata = metadata
        flag_modified(import_record, "import_metadata")
        import_record.status = ImportStatus.PROCESSING
        self.db.commit()

        return {
            "import_id": import_record.id,
            "is_multi_account": True,
            "account_count": len(results),
            "accounts": [
                self._format_single_result(import_record.id, r, index=i)
                for i, r in enumerate(results)
            ],
            "total_value": sum(float(r.total_value) for r in results if r.success),
        }

    def _format_single_result(
        self,
        import_id: str,
        result: BrokerageParseResult,
        index: int = 0
    ) -> Dict[str, Any]:
        """Format a single parse result for API response."""
        return {
            "import_id": import_id,
            "account_index": index,
            "provider": result.provider,
            "account_type": result.account_type,
            "account_identifier": result.account_identifier,
            "account_alias": result.raw_metadata.get("account_alias", "") if hasattr(result, "raw_metadata") and result.raw_metadata else "",
            "statement_date": result.statement_date.isoformat() if result.statement_date else None,
            "total_value": float(result.total_value),
            "total_cash": float(result.total_cash),
            "total_securities": float(result.total_securities),
            "calculated_total": float(result.calculated_total),
            "is_reconciled": result.is_reconciled,
            "reconciliation_diff": float(result.reconciliation_diff),
            "positions": [
                {
                    "symbol": p.symbol,
                    "security_name": p.security_name,
                    "security_type": p.security_type,
                    "quantity": float(p.quantity) if p.quantity else None,
                    "price": float(p.price) if p.price else None,
                    "market_value": float(p.market_value),
                    "cost_basis": float(p.cost_basis) if p.cost_basis else None,
                    "asset_class": p.asset_class,
                    "currency": p.currency,
                    "market_value_usd": float(p.market_value_usd) if p.market_value_usd else None,
                    "fx_rate_used": float(p.fx_rate_used) if p.fx_rate_used else None,
                }
                for p in result.positions
            ],
            "warnings": result.warnings,
            "base_currency": result.base_currency,
            "fx_rates": {k: float(v) for k, v in result.fx_rates.items()} if result.fx_rates else {},
            "cash_by_currency": {k: float(v) for k, v in result.cash_by_currency.items()} if result.cash_by_currency else {},
        }

    async def commit(
        self,
        import_id: str,
        account_id: Optional[str] = None,
        create_account: bool = True,
        account_name: Optional[str] = None,
        account_index: Optional[int] = None
    ) -> Dict[str, Any]:
        """Commit parsed holdings to database.

        Args:
            import_id: Import record ID
            account_id: Optional existing account ID
            create_account: If True, create new account if needed
            account_name: Name for new account
            account_index: For multi-account, which account to commit (None = all)

        Returns:
            Dict with snapshot ID and summary (or array for multi-account)
        """
        import_record = self.db.query(ImportRecord).filter(
            ImportRecord.id == import_id
        ).first()

        if not import_record:
            raise ValueError(f"Import record {import_id} not found")

        metadata = import_record.import_metadata or {}

        # Check for multi-account statement
        if metadata.get("is_multi_account"):
            return await self._commit_multi_account(
                import_record, metadata, account_index, create_account
            )

        parse_result = metadata.get("parse_result")

        if not parse_result:
            raise ValueError("Statement not parsed yet. Call parse first.")

        # Get or create account
        if account_id:
            account = self.db.query(Account).filter(Account.id == account_id).first()
            if not account:
                raise ValueError(f"Account {account_id} not found")
        else:
            # Try to find existing account with matching identifier and provider
            account = self._find_existing_account(parse_result)
            if not account and create_account:
                account = self._create_account_from_result(parse_result, account_name)
            elif not account:
                raise ValueError("No matching account found and create_account is False")

        # Update import record with account
        import_record.account_id = account.id

        # Get statement date
        statement_date_val = (
            datetime.fromisoformat(parse_result["statement_date"]).date()
            if parse_result.get("statement_date")
            else date.today()
        )

        # Create holdings snapshot
        snapshot = HoldingsSnapshot(
            account_id=account.id,
            import_id=import_record.id,
            statement_date=statement_date_val,
            statement_start_date=datetime.fromisoformat(parse_result["statement_start_date"]).date() if parse_result.get("statement_start_date") else None,
            total_value=Decimal(str(parse_result["total_value"])),
            total_cash=Decimal(str(parse_result["total_cash"])),
            total_securities=Decimal(str(parse_result["total_securities"])),
            calculated_total=Decimal(str(parse_result["calculated_total"])),
            is_reconciled=parse_result["is_reconciled"],
            reconciliation_diff=Decimal(str(parse_result["reconciliation_diff"])),
            source_file_hash=import_record.file_hash,
            raw_metadata=parse_result,
            # Multi-currency support
            base_currency=parse_result.get("base_currency", "USD"),
            cash_balances=parse_result.get("cash_by_currency"),
        )

        self.db.add(snapshot)
        self.db.flush()  # Get snapshot ID

        # Create FX rates if present
        fx_rates = parse_result.get("fx_rates", {})
        for currency, rate in fx_rates.items():
            if currency != "USD":  # Don't store USD/USD rate
                fx_rate = FxRate(
                    snapshot_id=snapshot.id,
                    from_currency=currency,
                    to_currency="USD",
                    rate=Decimal(str(rate)),
                    rate_date=statement_date_val,
                    source="statement",
                )
                self.db.add(fx_rate)

        # Create positions
        for idx, pos_data in enumerate(parse_result.get("positions", [])):
            position = Position(
                snapshot_id=snapshot.id,
                symbol=pos_data.get("symbol"),
                security_name=pos_data["security_name"],
                security_type=PositionType(pos_data.get("security_type", "OTHER")),
                quantity=Decimal(str(pos_data["quantity"])) if pos_data.get("quantity") else None,
                price=Decimal(str(pos_data["price"])) if pos_data.get("price") else None,
                market_value=Decimal(str(pos_data["market_value"])),
                cost_basis=Decimal(str(pos_data["cost_basis"])) if pos_data.get("cost_basis") else None,
                asset_class=AssetClass(pos_data.get("asset_class", "UNKNOWN")),
                row_index=idx,
                # Multi-currency support
                currency=pos_data.get("currency", "USD"),
                market_value_usd=Decimal(str(pos_data["market_value_usd"])) if pos_data.get("market_value_usd") else None,
                fx_rate_used=Decimal(str(pos_data["fx_rate_used"])) if pos_data.get("fx_rate_used") else None,
            )
            self.db.add(position)

        # Update import record status
        import_record.status = ImportStatus.SUCCESS
        import_record.completed_at = datetime.utcnow()

        # Clean up temp file
        temp_path = metadata.get("temp_path")
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

        self.db.commit()

        return {
            "snapshot_id": snapshot.id,
            "account_id": account.id,
            "account_name": account.name,
            "statement_date": snapshot.statement_date.isoformat(),
            "total_value": float(snapshot.total_value),
            "position_count": len(parse_result.get("positions", [])),
            "is_reconciled": snapshot.is_reconciled,
        }

    async def _commit_multi_account(
        self,
        import_record: ImportRecord,
        metadata: Dict[str, Any],
        account_index: Optional[int],
        create_account: bool
    ) -> Dict[str, Any]:
        """Commit multi-account IBKR statement.

        Args:
            import_record: The import record
            metadata: Import metadata with parse_results array
            account_index: If specified, only commit this account index
            create_account: Whether to create new accounts

        Returns:
            Dict with array of commit results
        """
        parse_results = metadata.get("parse_results", [])
        if not parse_results:
            raise ValueError("No parse results found. Call parse first.")

        # If account_index specified, only commit that account
        if account_index is not None:
            if account_index >= len(parse_results):
                raise ValueError(f"Account index {account_index} out of range (0-{len(parse_results)-1})")
            parse_results = [(account_index, parse_results[account_index])]
        else:
            parse_results = list(enumerate(parse_results))

        results = []
        for idx, parse_result in parse_results:
            result = self._commit_single_account(
                import_record, parse_result, create_account, idx
            )
            results.append(result)

        # Update import record status
        import_record.status = ImportStatus.SUCCESS
        import_record.completed_at = datetime.utcnow()

        # Clean up temp file (only when all accounts committed)
        if account_index is None:
            temp_path = metadata.get("temp_path")
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

        self.db.commit()

        return {
            "is_multi_account": True,
            "accounts_committed": len(results),
            "total_value": sum(r["total_value"] for r in results),
            "results": results,
        }

    def _commit_single_account(
        self,
        import_record: ImportRecord,
        parse_result: Dict[str, Any],
        create_account: bool,
        account_index: int = 0
    ) -> Dict[str, Any]:
        """Commit a single account from parse result.

        Args:
            import_record: The import record
            parse_result: Parse result dict for this account
            create_account: Whether to create new account
            account_index: Index for account naming

        Returns:
            Dict with commit result
        """
        # Generate account name using alias if available
        account_alias = parse_result.get("raw_metadata", {}).get("account_alias", "")
        if account_alias:
            account_name = f"IBKR {account_alias} {parse_result['account_identifier']}"
        else:
            account_name = None

        # Try to find existing account first, then create if not found
        account = self._find_existing_account(parse_result)
        if not account and create_account:
            account = self._create_account_from_result(parse_result, account_name)
        elif not account:
            raise ValueError("No matching account found and create_account is False")

        # Get statement date
        statement_date_val = (
            datetime.fromisoformat(parse_result["statement_date"]).date()
            if parse_result.get("statement_date")
            else date.today()
        )

        # Create holdings snapshot
        snapshot = HoldingsSnapshot(
            account_id=account.id,
            import_id=import_record.id,
            statement_date=statement_date_val,
            statement_start_date=datetime.fromisoformat(parse_result["statement_start_date"]).date() if parse_result.get("statement_start_date") else None,
            total_value=Decimal(str(parse_result["total_value"])),
            total_cash=Decimal(str(parse_result["total_cash"])),
            total_securities=Decimal(str(parse_result["total_securities"])),
            calculated_total=Decimal(str(parse_result["calculated_total"])),
            is_reconciled=parse_result["is_reconciled"],
            reconciliation_diff=Decimal(str(parse_result["reconciliation_diff"])),
            source_file_hash=import_record.file_hash,
            raw_metadata=parse_result,
            # Multi-currency support
            base_currency=parse_result.get("base_currency", "USD"),
            cash_balances=parse_result.get("cash_by_currency"),
        )

        self.db.add(snapshot)
        self.db.flush()  # Get snapshot ID

        # Create FX rates if present
        fx_rates = parse_result.get("fx_rates", {})
        for currency, rate in fx_rates.items():
            if currency != "USD":  # Don't store USD/USD rate
                fx_rate = FxRate(
                    snapshot_id=snapshot.id,
                    from_currency=currency,
                    to_currency="USD",
                    rate=Decimal(str(rate)),
                    rate_date=statement_date_val,
                    source="statement",
                )
                self.db.add(fx_rate)

        # Create positions
        for idx, pos_data in enumerate(parse_result.get("positions", [])):
            position = Position(
                snapshot_id=snapshot.id,
                symbol=pos_data.get("symbol"),
                security_name=pos_data["security_name"],
                security_type=PositionType(pos_data.get("security_type", "OTHER")),
                quantity=Decimal(str(pos_data["quantity"])) if pos_data.get("quantity") else None,
                price=Decimal(str(pos_data["price"])) if pos_data.get("price") else None,
                market_value=Decimal(str(pos_data["market_value"])),
                cost_basis=Decimal(str(pos_data["cost_basis"])) if pos_data.get("cost_basis") else None,
                asset_class=AssetClass(pos_data.get("asset_class", "UNKNOWN")),
                row_index=idx,
                # Multi-currency support
                currency=pos_data.get("currency", "USD"),
                market_value_usd=Decimal(str(pos_data["market_value_usd"])) if pos_data.get("market_value_usd") else None,
                fx_rate_used=Decimal(str(pos_data["fx_rate_used"])) if pos_data.get("fx_rate_used") else None,
            )
            self.db.add(position)

        return {
            "snapshot_id": snapshot.id,
            "account_id": account.id,
            "account_name": account.name,
            "account_alias": account_alias,
            "statement_date": snapshot.statement_date.isoformat(),
            "total_value": float(snapshot.total_value),
            "position_count": len(parse_result.get("positions", [])),
            "is_reconciled": snapshot.is_reconciled,
        }

    def get_snapshots(
        self,
        account_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """Get holdings snapshots with optional filters.

        Args:
            account_id: Filter by account
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            List of snapshot summaries
        """
        query = self.db.query(HoldingsSnapshot).join(Account)

        # Filter by user
        if self.user_id:
            query = query.filter(Account.user_id == self.user_id)

        if account_id:
            query = query.filter(HoldingsSnapshot.account_id == account_id)
        if start_date:
            query = query.filter(HoldingsSnapshot.statement_date >= start_date)
        if end_date:
            query = query.filter(HoldingsSnapshot.statement_date <= end_date)

        snapshots = query.order_by(HoldingsSnapshot.statement_date.desc()).all()

        return [
            {
                "id": s.id,
                "account_id": s.account_id,
                "account_name": s.account.name,
                "account_type": s.account.account_type.value,
                "statement_date": s.statement_date.isoformat(),
                "total_value": float(s.total_value),
                "total_cash": float(s.total_cash),
                "total_securities": float(s.total_securities),
                "is_reconciled": s.is_reconciled,
                "position_count": len(s.positions),
            }
            for s in snapshots
        ]

    def get_snapshot_detail(self, snapshot_id: str) -> Dict[str, Any]:
        """Get snapshot with positions.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            Snapshot with full position details
        """
        snapshot = self.db.query(HoldingsSnapshot).filter(
            HoldingsSnapshot.id == snapshot_id
        ).first()

        if not snapshot:
            raise ValueError(f"Snapshot {snapshot_id} not found")

        return {
            "id": snapshot.id,
            "account_id": snapshot.account_id,
            "account_name": snapshot.account.name,
            "statement_date": snapshot.statement_date.isoformat(),
            "total_value": float(snapshot.total_value),
            "total_cash": float(snapshot.total_cash),
            "total_securities": float(snapshot.total_securities),
            "calculated_total": float(snapshot.calculated_total) if snapshot.calculated_total else None,
            "is_reconciled": snapshot.is_reconciled,
            "reconciliation_diff": float(snapshot.reconciliation_diff) if snapshot.reconciliation_diff else None,
            "positions": [
                {
                    "id": p.id,
                    "symbol": p.symbol,
                    "security_name": p.security_name,
                    "security_type": p.security_type.value if p.security_type else None,
                    "quantity": float(p.quantity) if p.quantity else None,
                    "price": float(p.price) if p.price else None,
                    "market_value": float(p.market_value),
                    "cost_basis": float(p.cost_basis) if p.cost_basis else None,
                    "asset_class": p.asset_class.value if p.asset_class else None,
                }
                for p in snapshot.positions
            ],
        }

    def get_net_worth(
        self,
        account_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Calculate net worth across brokerage accounts.

        Net worth at any date = sum of (latest snapshot per account as of that date).
        If an account has no snapshot on a given date, we carry forward its most recent value.

        Args:
            account_ids: Optional list of account IDs to include

        Returns:
            Current net worth and history
        """
        # Build base query filtering by user
        base_query = self.db.query(HoldingsSnapshot).join(Account)
        if self.user_id:
            base_query = base_query.filter(Account.user_id == self.user_id)

        # Get latest snapshot for each account (for current total)
        subquery = self.db.query(
            HoldingsSnapshot.account_id,
            func.max(HoldingsSnapshot.statement_date).label("max_date")
        ).join(Account)
        if self.user_id:
            subquery = subquery.filter(Account.user_id == self.user_id)
        subquery = subquery.group_by(HoldingsSnapshot.account_id).subquery()

        query = self.db.query(HoldingsSnapshot).join(Account).join(
            subquery,
            (HoldingsSnapshot.account_id == subquery.c.account_id) &
            (HoldingsSnapshot.statement_date == subquery.c.max_date)
        )
        if self.user_id:
            query = query.filter(Account.user_id == self.user_id)

        if account_ids:
            query = query.filter(HoldingsSnapshot.account_id.in_(account_ids))

        latest_snapshots = query.all()

        current_total = sum(float(s.total_value) for s in latest_snapshots)

        # Get all snapshots for history calculation
        all_snapshots_query = self.db.query(HoldingsSnapshot).join(Account)
        if self.user_id:
            all_snapshots_query = all_snapshots_query.filter(Account.user_id == self.user_id)
        if account_ids:
            all_snapshots_query = all_snapshots_query.filter(
                HoldingsSnapshot.account_id.in_(account_ids)
            )
        all_snapshots = all_snapshots_query.order_by(HoldingsSnapshot.statement_date).all()

        # Build history with carry-forward logic
        # For each unique date, net worth = sum of latest snapshot per account as of that date
        history = []
        if all_snapshots:
            # Get unique dates
            unique_dates = sorted(set(s.statement_date for s in all_snapshots))

            # Track latest value per account (carry-forward)
            account_latest_values: Dict[str, float] = {}

            # Group snapshots by date for efficient lookup
            from collections import defaultdict
            snapshots_by_date: Dict[date, List[HoldingsSnapshot]] = defaultdict(list)
            for s in all_snapshots:
                snapshots_by_date[s.statement_date].append(s)

            for d in unique_dates:
                # Update account values for snapshots on this date
                for s in snapshots_by_date[d]:
                    account_latest_values[s.account_id] = float(s.total_value)

                # Net worth = sum of all accounts' latest values
                total = sum(account_latest_values.values())
                history.append({
                    "date": d.isoformat(),
                    "total": total,
                })

        return {
            "current_total": current_total,
            "accounts": [
                {
                    "account_id": s.account_id,
                    "account_name": s.account.name,
                    "account_type": s.account.account_type.value,
                    "latest_value": float(s.total_value),
                    "statement_date": s.statement_date.isoformat(),
                }
                for s in latest_snapshots
            ],
            "history": history,
        }

    def get_net_worth_by_account(
        self,
        account_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Get net worth history broken down by account.

        Uses carry-forward logic: for each date, each account's value is its
        latest snapshot as of that date (or carried forward from earlier).

        Args:
            account_ids: Optional list of account IDs to include

        Returns:
            History with per-account values for stacked charts
        """
        from collections import defaultdict

        # Get all snapshots with account info
        query = self.db.query(HoldingsSnapshot).join(Account)

        # Filter by user
        if self.user_id:
            query = query.filter(Account.user_id == self.user_id)

        if account_ids:
            query = query.filter(HoldingsSnapshot.account_id.in_(account_ids))

        snapshots = query.order_by(HoldingsSnapshot.statement_date).all()

        if not snapshots:
            return {"accounts": [], "history": []}

        # Get unique dates and accounts
        unique_dates = sorted(set(s.statement_date for s in snapshots))

        # Build account info lookup
        all_accounts = {}
        for s in snapshots:
            if s.account_id not in all_accounts:
                all_accounts[s.account_id] = {
                    "account_id": s.account_id,
                    "account_name": s.account.name,
                    "account_type": s.account.account_type.value,
                }

        # Group snapshots by date
        snapshots_by_date: Dict[date, List[HoldingsSnapshot]] = defaultdict(list)
        for s in snapshots:
            snapshots_by_date[s.statement_date].append(s)

        # Build history with carry-forward logic
        account_latest_values: Dict[str, Dict] = {}  # account_id -> {account info + value}
        history = []

        for d in unique_dates:
            # Update account values for snapshots on this date
            for s in snapshots_by_date[d]:
                account_latest_values[s.account_id] = {
                    "account_id": s.account_id,
                    "account_name": s.account.name,
                    "account_type": s.account.account_type.value,
                    "value": float(s.total_value),
                }

            # Build accounts list for this date (all accounts with their current values)
            accounts_data = list(account_latest_values.values())
            total = sum(a["value"] for a in accounts_data)

            history.append({
                "date": d.isoformat(),
                "total": total,
                "accounts": accounts_data,
            })

        return {
            "accounts": list(all_accounts.values()),
            "history": history,
        }

    def get_asset_class_breakdown(
        self,
        account_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Get asset class breakdown of current holdings.

        Uses carry-forward logic: for each date, each account's positions are from its
        latest snapshot as of that date.

        Args:
            account_ids: Optional list of account IDs to include

        Returns:
            Current breakdown by asset class with history
        """
        from collections import defaultdict

        # Get latest snapshot for each account (for current breakdown)
        subquery = self.db.query(
            HoldingsSnapshot.account_id,
            func.max(HoldingsSnapshot.statement_date).label("max_date")
        ).join(Account)
        if self.user_id:
            subquery = subquery.filter(Account.user_id == self.user_id)
        subquery = subquery.group_by(HoldingsSnapshot.account_id).subquery()

        query = self.db.query(HoldingsSnapshot).join(Account).join(
            subquery,
            (HoldingsSnapshot.account_id == subquery.c.account_id) &
            (HoldingsSnapshot.statement_date == subquery.c.max_date)
        )
        if self.user_id:
            query = query.filter(Account.user_id == self.user_id)

        if account_ids:
            query = query.filter(HoldingsSnapshot.account_id.in_(account_ids))

        latest_snapshots = query.all()
        latest_snapshot_ids = [s.id for s in latest_snapshots]

        # Get positions from latest snapshots and aggregate by asset class
        current_breakdown = {
            "EQUITY": 0.0,
            "FIXED_INCOME": 0.0,
            "CASH": 0.0,
            "ALTERNATIVE": 0.0,
            "UNKNOWN": 0.0,
        }

        # Get total_value from snapshots (this is the true net worth)
        snapshot_total_value = sum(float(s.total_value) for s in latest_snapshots)

        if latest_snapshot_ids:
            positions = self.db.query(Position).filter(
                Position.snapshot_id.in_(latest_snapshot_ids)
            ).all()

            for p in positions:
                asset_class = p.asset_class.value if p.asset_class else "UNKNOWN"
                # Use market_value_usd for multi-currency support, fallback to market_value
                value = float(p.market_value_usd) if p.market_value_usd else float(p.market_value)
                current_breakdown[asset_class] += value

            # Calculate implied cash as difference between total_value and positions
            # This ensures the breakdown total matches net worth exactly
            position_total = sum(current_breakdown.values())
            implied_cash = snapshot_total_value - position_total
            if implied_cash > 0:
                current_breakdown["CASH"] += implied_cash

        current_total = sum(current_breakdown.values())

        # Get all snapshots for history calculation
        all_snapshots_query = self.db.query(HoldingsSnapshot).join(Account)
        if self.user_id:
            all_snapshots_query = all_snapshots_query.filter(Account.user_id == self.user_id)
        if account_ids:
            all_snapshots_query = all_snapshots_query.filter(
                HoldingsSnapshot.account_id.in_(account_ids)
            )
        all_snapshots = all_snapshots_query.order_by(HoldingsSnapshot.statement_date).all()

        if not all_snapshots:
            return {
                "current": {
                    "equity": 0.0,
                    "fixed_income": 0.0,
                    "cash": 0.0,
                    "alternative": 0.0,
                    "unknown": 0.0,
                    "total": 0.0,
                },
                "history": [],
            }

        # Get unique dates
        unique_dates = sorted(set(s.statement_date for s in all_snapshots))

        # Get positions for all snapshots
        all_snapshot_ids = [s.id for s in all_snapshots]
        all_positions = self.db.query(Position).filter(
            Position.snapshot_id.in_(all_snapshot_ids)
        ).all() if all_snapshot_ids else []

        # Map positions to snapshots
        snapshot_positions: Dict[str, List[Position]] = defaultdict(list)
        for p in all_positions:
            snapshot_positions[p.snapshot_id].append(p)

        # Map snapshot_id to snapshot object (for accessing total_cash)
        snapshot_by_id: Dict[str, HoldingsSnapshot] = {s.id: s for s in all_snapshots}

        # Group snapshots by date
        snapshots_by_date: Dict[date, List[HoldingsSnapshot]] = defaultdict(list)
        for s in all_snapshots:
            snapshots_by_date[s.statement_date].append(s)

        # Build history with carry-forward logic
        # Track latest snapshot ID per account
        account_latest_snapshot_id: Dict[str, str] = {}
        history = []

        for d in unique_dates:
            # Update latest snapshot per account for this date
            for s in snapshots_by_date[d]:
                account_latest_snapshot_id[s.account_id] = s.id

            # Aggregate positions from all accounts' latest snapshots
            breakdown = {
                "EQUITY": 0.0,
                "FIXED_INCOME": 0.0,
                "CASH": 0.0,
                "ALTERNATIVE": 0.0,
                "UNKNOWN": 0.0,
            }

            # Calculate total_value for this date (sum of latest snapshots per account)
            date_total_value = 0.0
            for snapshot_id in account_latest_snapshot_id.values():
                # Add positions (use market_value_usd for multi-currency support)
                for p in snapshot_positions.get(snapshot_id, []):
                    asset_class = p.asset_class.value if p.asset_class else "UNKNOWN"
                    value = float(p.market_value_usd) if p.market_value_usd else float(p.market_value)
                    breakdown[asset_class] += value

                # Track total_value from snapshot
                snapshot = snapshot_by_id.get(snapshot_id)
                if snapshot:
                    date_total_value += float(snapshot.total_value)

            # Calculate implied cash as difference between total_value and positions
            # This ensures the breakdown total matches net worth exactly
            position_total = sum(breakdown.values())
            implied_cash = date_total_value - position_total
            if implied_cash > 0:
                breakdown["CASH"] += implied_cash

            history.append({
                "date": d.isoformat(),
                "equity": breakdown["EQUITY"],
                "fixed_income": breakdown["FIXED_INCOME"],
                "cash": breakdown["CASH"],
                "alternative": breakdown["ALTERNATIVE"],
                "unknown": breakdown["UNKNOWN"],
                "total": sum(breakdown.values()),
            })

        return {
            "current": {
                "equity": current_breakdown["EQUITY"],
                "fixed_income": current_breakdown["FIXED_INCOME"],
                "cash": current_breakdown["CASH"],
                "alternative": current_breakdown["ALTERNATIVE"],
                "unknown": current_breakdown["UNKNOWN"],
                "total": current_total,
            },
            "history": history,
        }

    def _get_parser(self, provider: str, file_path: str):
        """Get appropriate parser for provider."""
        if provider == "fidelity":
            return FidelityBrokerageParser(file_path)
        elif provider == "schwab":
            return SchwabBrokerageParser(file_path)
        elif provider == "ibkr":
            return IBKRBrokerageParser(file_path)
        elif provider == "vanguard":
            return VanguardBrokerageParser(file_path)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def _find_existing_account(
        self,
        parse_result: Dict[str, Any]
    ) -> Optional[Account]:
        """Find existing account matching the parse result.

        Matches by account_number_last4 and institution (provider), filtered by user_id.
        This allows multiple imports to the same account to be linked together.
        """
        provider = parse_result.get("provider", "").title()
        account_identifier = parse_result.get("account_identifier", "")
        last4 = account_identifier[-4:] if len(account_identifier) >= 4 else None

        if not last4:
            return None

        # Find account with matching last4, institution, and user_id
        query = self.db.query(Account).filter(
            Account.account_number_last4 == last4,
            Account.institution == provider,
            Account.is_active == True
        )
        if self.user_id:
            query = query.filter(Account.user_id == self.user_id)
        account = query.first()

        return account

    def _create_account_from_result(
        self,
        parse_result: Dict[str, Any],
        account_name: Optional[str] = None
    ) -> Account:
        """Create account from parse result."""
        provider = parse_result.get("provider", "").title()
        account_type_str = parse_result.get("account_type", "BROKERAGE")
        account_identifier = parse_result.get("account_identifier", "")

        # Map account type string to enum
        account_type_map = {
            "BROKERAGE": AccountType.BROKERAGE,
            "IRA_ROTH": AccountType.IRA_ROTH,
            "IRA_TRADITIONAL": AccountType.IRA_TRADITIONAL,
            "RETIREMENT_401K": AccountType.RETIREMENT_401K,
            "STOCK_PLAN": AccountType.STOCK_PLAN,
        }
        account_type = account_type_map.get(account_type_str, AccountType.BROKERAGE)

        # Generate name if not provided
        if not account_name:
            type_names = {
                AccountType.BROKERAGE: "Brokerage",
                AccountType.IRA_ROTH: "Roth IRA",
                AccountType.IRA_TRADITIONAL: "Traditional IRA",
                AccountType.RETIREMENT_401K: "401(k)",
                AccountType.STOCK_PLAN: "Stock Plan",
            }
            type_name = type_names.get(account_type, "Investment")
            account_name = f"{provider} {type_name} {account_identifier}"

        account = Account(
            name=account_name,
            institution=provider,
            account_type=account_type,
            account_number_last4=account_identifier[-4:] if len(account_identifier) >= 4 else None,
            user_id=self.user_id,
        )

        self.db.add(account)
        self.db.flush()

        return account

    def _result_to_dict(self, result: BrokerageParseResult) -> Dict[str, Any]:
        """Convert BrokerageParseResult to serializable dict."""
        return {
            "provider": result.provider,
            "account_type": result.account_type,
            "account_identifier": result.account_identifier,
            "statement_date": result.statement_date.isoformat() if result.statement_date else None,
            "statement_start_date": result.statement_start_date.isoformat() if result.statement_start_date else None,
            "total_value": str(result.total_value),
            "total_cash": str(result.total_cash),
            "total_securities": str(result.total_securities),
            "calculated_total": str(result.calculated_total),
            "is_reconciled": result.is_reconciled,
            "reconciliation_diff": str(result.reconciliation_diff),
            "positions": [
                {
                    "symbol": p.symbol,
                    "cusip": p.cusip,
                    "security_name": p.security_name,
                    "security_type": p.security_type,
                    "quantity": str(p.quantity) if p.quantity else None,
                    "price": str(p.price) if p.price else None,
                    "market_value": str(p.market_value),
                    "cost_basis": str(p.cost_basis) if p.cost_basis else None,
                    "asset_class": p.asset_class,
                    "row_index": p.row_index,
                    # Multi-currency support
                    "currency": p.currency,
                    "market_value_usd": str(p.market_value_usd) if p.market_value_usd else None,
                    "fx_rate_used": str(p.fx_rate_used) if p.fx_rate_used else None,
                }
                for p in result.positions
            ],
            "errors": result.errors,
            "warnings": result.warnings,
            # Multi-currency support
            "base_currency": result.base_currency,
            "fx_rates": {k: str(v) for k, v in result.fx_rates.items()} if result.fx_rates else {},
            "cash_by_currency": {k: str(v) for k, v in result.cash_by_currency.items()} if result.cash_by_currency else {},
        }
