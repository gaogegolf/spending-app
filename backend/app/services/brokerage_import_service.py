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
from app.services.file_parser.brokerage_parser import (
    BrokerageParseResult,
    PositionData,
    detect_brokerage_provider,
)
from app.services.file_parser.fidelity_brokerage_parser import FidelityBrokerageParser
from app.services.file_parser.schwab_brokerage_parser import SchwabBrokerageParser
from app.config import settings

logger = logging.getLogger(__name__)


class BrokerageImportService:
    """Service to orchestrate brokerage statement import."""

    def __init__(self, db: Session):
        """Initialize brokerage import service."""
        self.db = db
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
                "Currently supported: Fidelity, Schwab"
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
            Dict with parsed holdings preview
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

        # Parse the statement
        result = parser.parse()

        if not result.success:
            import_record.status = ImportStatus.FAILED
            import_record.error_message = "; ".join(result.errors)
            self.db.commit()
            raise ValueError(f"Failed to parse statement: {'; '.join(result.errors)}")

        # Store parse result in metadata for commit
        metadata["parse_result"] = self._result_to_dict(result)
        import_record.import_metadata = metadata
        flag_modified(import_record, "import_metadata")  # Ensure SQLAlchemy detects JSON change
        import_record.status = ImportStatus.PROCESSING
        self.db.commit()

        return {
            "import_id": import_id,
            "provider": result.provider,
            "account_type": result.account_type,
            "account_identifier": result.account_identifier,
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
                }
                for p in result.positions
            ],
            "warnings": result.warnings,
        }

    async def commit(
        self,
        import_id: str,
        account_id: Optional[str] = None,
        create_account: bool = True,
        account_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Commit parsed holdings to database.

        Args:
            import_id: Import record ID
            account_id: Optional existing account ID
            create_account: If True, create new account if needed
            account_name: Name for new account

        Returns:
            Dict with snapshot ID and summary
        """
        import_record = self.db.query(ImportRecord).filter(
            ImportRecord.id == import_id
        ).first()

        if not import_record:
            raise ValueError(f"Import record {import_id} not found")

        metadata = import_record.import_metadata or {}
        parse_result = metadata.get("parse_result")

        if not parse_result:
            raise ValueError("Statement not parsed yet. Call parse first.")

        # Get or create account
        if account_id:
            account = self.db.query(Account).filter(Account.id == account_id).first()
            if not account:
                raise ValueError(f"Account {account_id} not found")
        elif create_account:
            account = self._create_account_from_result(parse_result, account_name)
        else:
            raise ValueError("No account specified and create_account is False")

        # Update import record with account
        import_record.account_id = account.id

        # Create holdings snapshot
        snapshot = HoldingsSnapshot(
            account_id=account.id,
            import_id=import_record.id,
            statement_date=datetime.fromisoformat(parse_result["statement_date"]).date() if parse_result.get("statement_date") else date.today(),
            statement_start_date=datetime.fromisoformat(parse_result["statement_start_date"]).date() if parse_result.get("statement_start_date") else None,
            total_value=Decimal(str(parse_result["total_value"])),
            total_cash=Decimal(str(parse_result["total_cash"])),
            total_securities=Decimal(str(parse_result["total_securities"])),
            calculated_total=Decimal(str(parse_result["calculated_total"])),
            is_reconciled=parse_result["is_reconciled"],
            reconciliation_diff=Decimal(str(parse_result["reconciliation_diff"])),
            source_file_hash=import_record.file_hash,
            raw_metadata=parse_result,
        )

        self.db.add(snapshot)
        self.db.flush()  # Get snapshot ID

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

        Args:
            account_ids: Optional list of account IDs to include

        Returns:
            Current net worth and history
        """
        # Get latest snapshot for each account
        subquery = self.db.query(
            HoldingsSnapshot.account_id,
            func.max(HoldingsSnapshot.statement_date).label("max_date")
        ).group_by(HoldingsSnapshot.account_id).subquery()

        query = self.db.query(HoldingsSnapshot).join(
            subquery,
            (HoldingsSnapshot.account_id == subquery.c.account_id) &
            (HoldingsSnapshot.statement_date == subquery.c.max_date)
        )

        if account_ids:
            query = query.filter(HoldingsSnapshot.account_id.in_(account_ids))

        latest_snapshots = query.all()

        current_total = sum(float(s.total_value) for s in latest_snapshots)

        # Get history (all snapshots, summed by date)
        history_query = self.db.query(
            HoldingsSnapshot.statement_date,
            func.sum(HoldingsSnapshot.total_value).label("total")
        )
        if account_ids:
            history_query = history_query.filter(HoldingsSnapshot.account_id.in_(account_ids))

        history = history_query.group_by(
            HoldingsSnapshot.statement_date
        ).order_by(HoldingsSnapshot.statement_date).all()

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
            "history": [
                {
                    "date": h.statement_date.isoformat(),
                    "total": float(h.total),
                }
                for h in history
            ],
        }

    def _get_parser(self, provider: str, file_path: str):
        """Get appropriate parser for provider."""
        if provider == "fidelity":
            return FidelityBrokerageParser(file_path)
        elif provider == "schwab":
            return SchwabBrokerageParser(file_path)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

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
                }
                for p in result.positions
            ],
            "errors": result.errors,
            "warnings": result.warnings,
        }
