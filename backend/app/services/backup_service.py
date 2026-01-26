"""Service for full data backup/export operations."""

import io
import json
import zipfile
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.rule import Rule
from app.models.merchant_category import MerchantCategory
from app.models.import_record import ImportRecord
from app.models.holdings_snapshot import HoldingsSnapshot
from app.models.position import Position
from app.models.fx_rate import FxRate


class BackupService:
    """Service for generating full data backups."""

    VERSION = "1.0"

    def __init__(self, db: Session):
        """Initialize backup service.

        Args:
            db: Database session
        """
        self.db = db

    def export_full_backup(
        self,
        user_id: str,
        username: str,
        as_zip: bool = False
    ) -> io.BytesIO:
        """Export all user data as JSON or ZIP.

        Args:
            user_id: User ID to export
            username: Username for metadata
            as_zip: If True, return ZIP with multiple JSON files

        Returns:
            BytesIO buffer with export content
        """
        data = self._collect_all_data(user_id, username)

        if as_zip:
            return self._create_zip_archive(data)
        else:
            return self._create_json_export(data)

    def get_backup_preview(self, user_id: str) -> Dict[str, Any]:
        """Get preview of what will be included in backup.

        Args:
            user_id: User ID

        Returns:
            Dictionary with data counts
        """
        accounts = self.db.query(Account).filter(Account.user_id == user_id).all()
        account_ids = [a.id for a in accounts]

        transaction_count = 0
        import_count = 0
        snapshot_count = 0
        position_count = 0
        fx_rate_count = 0

        if account_ids:
            transaction_count = self.db.query(Transaction).filter(
                Transaction.account_id.in_(account_ids)
            ).count()

            import_count = self.db.query(ImportRecord).filter(
                ImportRecord.account_id.in_(account_ids)
            ).count()

            snapshots = self.db.query(HoldingsSnapshot).filter(
                HoldingsSnapshot.account_id.in_(account_ids)
            ).all()
            snapshot_count = len(snapshots)
            snapshot_ids = [s.id for s in snapshots]

            if snapshot_ids:
                position_count = self.db.query(Position).filter(
                    Position.snapshot_id.in_(snapshot_ids)
                ).count()

                fx_rate_count = self.db.query(FxRate).filter(
                    FxRate.snapshot_id.in_(snapshot_ids)
                ).count()

        rule_count = self.db.query(Rule).filter(Rule.user_id == user_id).count()
        merchant_category_count = self.db.query(MerchantCategory).filter(
            MerchantCategory.user_id == user_id
        ).count()

        return {
            "data_counts": {
                "accounts": len(accounts),
                "transactions": transaction_count,
                "rules": rule_count,
                "merchant_categories": merchant_category_count,
                "import_records": import_count,
                "holdings_snapshots": snapshot_count,
                "positions": position_count,
                "fx_rates": fx_rate_count,
            }
        }

    def _collect_all_data(self, user_id: str, username: str) -> Dict[str, Any]:
        """Collect all user data from database.

        Args:
            user_id: User ID
            username: Username for metadata

        Returns:
            Dictionary with all user data
        """
        # Query all entities filtered by user_id
        accounts = self.db.query(Account).filter(Account.user_id == user_id).all()
        account_ids = [a.id for a in accounts]

        transactions = []
        import_records = []
        holdings_snapshots = []
        positions = []
        fx_rates = []

        if account_ids:
            transactions = self.db.query(Transaction).filter(
                Transaction.account_id.in_(account_ids)
            ).all()

            import_records = self.db.query(ImportRecord).filter(
                ImportRecord.account_id.in_(account_ids)
            ).all()

            holdings_snapshots = self.db.query(HoldingsSnapshot).filter(
                HoldingsSnapshot.account_id.in_(account_ids)
            ).all()

            snapshot_ids = [s.id for s in holdings_snapshots]
            if snapshot_ids:
                positions = self.db.query(Position).filter(
                    Position.snapshot_id.in_(snapshot_ids)
                ).all()

                fx_rates = self.db.query(FxRate).filter(
                    FxRate.snapshot_id.in_(snapshot_ids)
                ).all()

        rules = self.db.query(Rule).filter(Rule.user_id == user_id).all()
        merchant_categories = self.db.query(MerchantCategory).filter(
            MerchantCategory.user_id == user_id
        ).all()

        return {
            "export_metadata": {
                "version": self.VERSION,
                "export_date": datetime.utcnow().isoformat() + "Z",
                "app_version": "1.0.0",
                "user_id": user_id,
                "username": username,
                "data_counts": {
                    "accounts": len(accounts),
                    "transactions": len(transactions),
                    "rules": len(rules),
                    "merchant_categories": len(merchant_categories),
                    "import_records": len(import_records),
                    "holdings_snapshots": len(holdings_snapshots),
                    "positions": len(positions),
                    "fx_rates": len(fx_rates),
                }
            },
            "accounts": [self._serialize_account(a) for a in accounts],
            "transactions": [self._serialize_transaction(t) for t in transactions],
            "rules": [self._serialize_rule(r) for r in rules],
            "merchant_categories": [self._serialize_merchant_category(mc) for mc in merchant_categories],
            "import_records": [self._serialize_import_record(ir) for ir in import_records],
            "holdings_snapshots": [self._serialize_holdings_snapshot(hs) for hs in holdings_snapshots],
            "positions": [self._serialize_position(p) for p in positions],
            "fx_rates": [self._serialize_fx_rate(fx) for fx in fx_rates],
        }

    def _create_json_export(self, data: Dict[str, Any]) -> io.BytesIO:
        """Create single JSON file export.

        Args:
            data: Collected data dictionary

        Returns:
            BytesIO buffer with JSON content
        """
        output = io.BytesIO()
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        output.write(json_str.encode('utf-8'))
        output.seek(0)
        return output

    def _create_zip_archive(self, data: Dict[str, Any]) -> io.BytesIO:
        """Create ZIP archive with separate JSON files.

        Args:
            data: Collected data dictionary

        Returns:
            BytesIO buffer with ZIP content
        """
        output = io.BytesIO()

        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Metadata file
            zf.writestr('metadata.json', json.dumps(data['export_metadata'], indent=2))

            # Individual data files
            zf.writestr('accounts.json', json.dumps(data['accounts'], indent=2))
            zf.writestr('transactions.json', json.dumps(data['transactions'], indent=2))
            zf.writestr('rules.json', json.dumps(data['rules'], indent=2))
            zf.writestr('merchant_categories.json', json.dumps(data['merchant_categories'], indent=2))
            zf.writestr('import_records.json', json.dumps(data['import_records'], indent=2))
            zf.writestr('holdings_snapshots.json', json.dumps(data['holdings_snapshots'], indent=2))
            zf.writestr('positions.json', json.dumps(data['positions'], indent=2))
            zf.writestr('fx_rates.json', json.dumps(data['fx_rates'], indent=2))

        output.seek(0)
        return output

    # Serialization methods

    def _serialize_value(self, value: Any) -> Any:
        """Serialize a value to JSON-compatible format.

        Args:
            value: Value to serialize

        Returns:
            JSON-compatible value
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat() + "Z"
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if hasattr(value, 'value'):  # Enum
            return value.value
        return value

    def _serialize_account(self, account: Account) -> Dict[str, Any]:
        """Serialize an Account to dictionary."""
        return {
            "id": account.id,
            "name": account.name,
            "institution": account.institution,
            "account_type": self._serialize_value(account.account_type),
            "account_number_last4": account.account_number_last4,
            "currency": account.currency,
            "is_active": account.is_active,
            "created_at": self._serialize_value(account.created_at),
            "updated_at": self._serialize_value(account.updated_at),
        }

    def _serialize_transaction(self, txn: Transaction) -> Dict[str, Any]:
        """Serialize a Transaction to dictionary."""
        return {
            "id": txn.id,
            "account_id": txn.account_id,
            "import_id": txn.import_id,
            "hash_dedup_key": txn.hash_dedup_key,
            "date": self._serialize_value(txn.date),
            "post_date": self._serialize_value(txn.post_date),
            "description_raw": txn.description_raw,
            "merchant_normalized": txn.merchant_normalized,
            "amount": self._serialize_value(txn.amount),
            "currency": txn.currency,
            "transaction_type": self._serialize_value(txn.transaction_type),
            "category": txn.category,
            "subcategory": txn.subcategory,
            "tags": txn.tags,
            "is_spend": txn.is_spend,
            "is_income": txn.is_income,
            "confidence": self._serialize_value(txn.confidence),
            "needs_review": txn.needs_review,
            "reviewed_at": self._serialize_value(txn.reviewed_at),
            "matched_rule_id": txn.matched_rule_id,
            "classification_method": self._serialize_value(txn.classification_method),
            "user_note": txn.user_note,
            "transaction_metadata": txn.transaction_metadata,
            "created_at": self._serialize_value(txn.created_at),
            "updated_at": self._serialize_value(txn.updated_at),
        }

    def _serialize_rule(self, rule: Rule) -> Dict[str, Any]:
        """Serialize a Rule to dictionary."""
        return {
            "id": rule.id,
            "rule_type": self._serialize_value(rule.rule_type),
            "pattern": rule.pattern,
            "action": rule.action,
            "priority": rule.priority,
            "is_active": rule.is_active,
            "match_count": rule.match_count,
            "name": rule.name,
            "description": rule.description,
            "created_at": self._serialize_value(rule.created_at),
            "updated_at": self._serialize_value(rule.updated_at),
            "last_matched_at": self._serialize_value(rule.last_matched_at),
        }

    def _serialize_merchant_category(self, mc: MerchantCategory) -> Dict[str, Any]:
        """Serialize a MerchantCategory to dictionary."""
        return {
            "id": mc.id,
            "merchant_normalized": mc.merchant_normalized,
            "category": mc.category,
            "confidence": mc.confidence,
            "source": mc.source,
            "times_applied": mc.times_applied,
            "created_at": self._serialize_value(mc.created_at),
            "updated_at": self._serialize_value(mc.updated_at),
        }

    def _serialize_import_record(self, ir: ImportRecord) -> Dict[str, Any]:
        """Serialize an ImportRecord to dictionary."""
        return {
            "id": ir.id,
            "account_id": ir.account_id,
            "source_type": self._serialize_value(ir.source_type),
            "filename": ir.filename,
            "file_size_bytes": ir.file_size_bytes,
            "file_hash": ir.file_hash,
            "status": self._serialize_value(ir.status),
            "error_message": ir.error_message,
            "transactions_imported": ir.transactions_imported,
            "transactions_duplicate": ir.transactions_duplicate,
            "import_metadata": ir.import_metadata,
            "created_at": self._serialize_value(ir.created_at),
            "completed_at": self._serialize_value(ir.completed_at),
        }

    def _serialize_holdings_snapshot(self, hs: HoldingsSnapshot) -> Dict[str, Any]:
        """Serialize a HoldingsSnapshot to dictionary."""
        return {
            "id": hs.id,
            "account_id": hs.account_id,
            "import_id": hs.import_id,
            "statement_date": self._serialize_value(hs.statement_date),
            "statement_start_date": self._serialize_value(hs.statement_start_date),
            "total_value": self._serialize_value(hs.total_value),
            "total_cash": self._serialize_value(hs.total_cash),
            "total_securities": self._serialize_value(hs.total_securities),
            "calculated_total": self._serialize_value(hs.calculated_total),
            "is_reconciled": hs.is_reconciled,
            "reconciliation_diff": self._serialize_value(hs.reconciliation_diff),
            "base_currency": hs.base_currency,
            "cash_balances": hs.cash_balances,
            "currency": hs.currency,
            "source_file_hash": hs.source_file_hash,
            "raw_metadata": hs.raw_metadata,
            "created_at": self._serialize_value(hs.created_at),
        }

    def _serialize_position(self, pos: Position) -> Dict[str, Any]:
        """Serialize a Position to dictionary."""
        return {
            "id": pos.id,
            "snapshot_id": pos.snapshot_id,
            "symbol": pos.symbol,
            "cusip": pos.cusip,
            "security_name": pos.security_name,
            "security_type": self._serialize_value(pos.security_type),
            "quantity": self._serialize_value(pos.quantity),
            "price": self._serialize_value(pos.price),
            "market_value": self._serialize_value(pos.market_value),
            "cost_basis": self._serialize_value(pos.cost_basis),
            "market_value_usd": self._serialize_value(pos.market_value_usd),
            "fx_rate_used": self._serialize_value(pos.fx_rate_used),
            "is_vested": pos.is_vested,
            "vesting_date": self._serialize_value(pos.vesting_date),
            "asset_class": self._serialize_value(pos.asset_class),
            "currency": pos.currency,
            "row_index": pos.row_index,
        }

    def _serialize_fx_rate(self, fx: FxRate) -> Dict[str, Any]:
        """Serialize an FxRate to dictionary."""
        return {
            "id": fx.id,
            "snapshot_id": fx.snapshot_id,
            "from_currency": fx.from_currency,
            "to_currency": fx.to_currency,
            "rate": self._serialize_value(fx.rate),
            "rate_date": self._serialize_value(fx.rate_date),
            "source": fx.source,
        }

    # ========== RESTORE METHODS ==========

    def restore_from_backup(
        self,
        user_id: str,
        backup_data: Dict[str, Any],
        conflict_mode: str = "skip"
    ) -> Dict[str, Any]:
        """Restore user data from backup.

        Args:
            user_id: User performing restore (data will belong to this user)
            backup_data: Parsed backup JSON data
            conflict_mode: How to handle duplicates
                - "skip": Skip existing records
                - "error": Fail on any conflict

        Returns:
            Summary with status, message, details per entity, and errors
        """
        errors = self._validate_backup(backup_data)
        if errors:
            return {
                "status": "error",
                "message": "Invalid backup file",
                "details": {},
                "errors": errors
            }

        results = {
            "accounts": {"created": 0, "skipped": 0, "errors": 0},
            "rules": {"created": 0, "skipped": 0, "errors": 0},
            "merchant_categories": {"created": 0, "skipped": 0, "errors": 0},
            "import_records": {"created": 0, "skipped": 0, "errors": 0},
            "transactions": {"created": 0, "skipped": 0, "errors": 0},
            "holdings_snapshots": {"created": 0, "skipped": 0, "errors": 0},
            "positions": {"created": 0, "skipped": 0, "errors": 0},
            "fx_rates": {"created": 0, "skipped": 0, "errors": 0},
        }
        all_errors: List[str] = []

        try:
            # Restore in dependency order, building ID maps
            # 1. Accounts (no dependencies)
            account_id_map, acct_result, acct_errors = self._restore_accounts(
                user_id, backup_data.get("accounts", []), conflict_mode
            )
            results["accounts"] = acct_result
            all_errors.extend(acct_errors)

            # 2. Rules (no dependencies)
            rule_id_map, rule_result, rule_errors = self._restore_rules(
                user_id, backup_data.get("rules", []), conflict_mode
            )
            results["rules"] = rule_result
            all_errors.extend(rule_errors)

            # 3. Merchant categories (no dependencies)
            mc_result, mc_errors = self._restore_merchant_categories(
                user_id, backup_data.get("merchant_categories", []), conflict_mode
            )
            results["merchant_categories"] = mc_result
            all_errors.extend(mc_errors)

            # 4. Import records (depends on accounts)
            import_id_map, ir_result, ir_errors = self._restore_import_records(
                backup_data.get("import_records", []), account_id_map, conflict_mode
            )
            results["import_records"] = ir_result
            all_errors.extend(ir_errors)

            # 5. Transactions (depends on accounts, import_records, rules)
            txn_result, txn_errors = self._restore_transactions(
                backup_data.get("transactions", []),
                account_id_map, import_id_map, rule_id_map, conflict_mode
            )
            results["transactions"] = txn_result
            all_errors.extend(txn_errors)

            # 6. Holdings snapshots (depends on accounts, import_records)
            snapshot_id_map, hs_result, hs_errors = self._restore_holdings_snapshots(
                backup_data.get("holdings_snapshots", []),
                account_id_map, import_id_map, conflict_mode
            )
            results["holdings_snapshots"] = hs_result
            all_errors.extend(hs_errors)

            # 7. Positions (depends on holdings_snapshots)
            pos_result, pos_errors = self._restore_positions(
                backup_data.get("positions", []), snapshot_id_map, conflict_mode
            )
            results["positions"] = pos_result
            all_errors.extend(pos_errors)

            # 8. FX rates (depends on holdings_snapshots)
            fx_result, fx_errors = self._restore_fx_rates(
                backup_data.get("fx_rates", []), snapshot_id_map, conflict_mode
            )
            results["fx_rates"] = fx_result
            all_errors.extend(fx_errors)

            self.db.commit()

        except Exception as e:
            self.db.rollback()
            return {
                "status": "error",
                "message": f"Restore failed: {str(e)}",
                "details": results,
                "errors": all_errors + [str(e)]
            }

        # Build summary message
        total_created = sum(r["created"] for r in results.values())
        total_skipped = sum(r["skipped"] for r in results.values())

        if all_errors:
            status = "partial"
            message = f"Restored {total_created} records with {len(all_errors)} errors"
        elif total_skipped > 0:
            status = "success"
            message = f"Restored {total_created} records, skipped {total_skipped} duplicates"
        else:
            status = "success"
            message = f"Restored {total_created} records successfully"

        return {
            "status": status,
            "message": message,
            "details": results,
            "errors": all_errors
        }

    def _validate_backup(self, backup_data: Dict[str, Any]) -> List[str]:
        """Validate backup structure and version.

        Args:
            backup_data: Parsed backup data

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not isinstance(backup_data, dict):
            return ["Backup data must be a JSON object"]

        # Check metadata
        metadata = backup_data.get("export_metadata")
        if not metadata:
            errors.append("Missing export_metadata")
        else:
            version = metadata.get("version")
            if not version:
                errors.append("Missing version in metadata")
            elif version != self.VERSION:
                errors.append(f"Unsupported backup version: {version} (expected {self.VERSION})")

        # Check required data arrays exist (can be empty)
        required_keys = ["accounts", "transactions", "rules", "merchant_categories"]
        for key in required_keys:
            if key not in backup_data:
                errors.append(f"Missing '{key}' in backup data")
            elif not isinstance(backup_data[key], list):
                errors.append(f"'{key}' must be an array")

        return errors

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime string to datetime object."""
        if not value:
            return None
        # Handle both with and without Z suffix
        value = value.rstrip("Z")
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _parse_date(self, value: Optional[str]) -> Optional[date]:
        """Parse ISO date string to date object."""
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _parse_decimal(self, value: Optional[str]) -> Optional[Decimal]:
        """Parse string to Decimal."""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except:
            return None

    def _restore_accounts(
        self,
        user_id: str,
        accounts: List[Dict],
        conflict_mode: str
    ) -> tuple[Dict[str, str], Dict[str, int], List[str]]:
        """Restore accounts.

        Returns:
            Tuple of (id_map, result_counts, errors)
        """
        id_map: Dict[str, str] = {}  # old_id -> new_id (same if preserved)
        result = {"created": 0, "skipped": 0, "errors": 0}
        errors: List[str] = []

        for acct_data in accounts:
            old_id = acct_data.get("id")
            if not old_id:
                errors.append("Account missing ID")
                result["errors"] += 1
                continue

            # Check if already exists
            existing = self.db.query(Account).filter(Account.id == old_id).first()
            if existing:
                if conflict_mode == "error":
                    errors.append(f"Account {old_id} already exists")
                    result["errors"] += 1
                else:
                    id_map[old_id] = old_id
                    result["skipped"] += 1
                continue

            try:
                account = Account(
                    id=old_id,
                    user_id=user_id,
                    name=acct_data.get("name"),
                    institution=acct_data.get("institution"),
                    account_type=acct_data.get("account_type"),
                    account_number_last4=acct_data.get("account_number_last4"),
                    currency=acct_data.get("currency", "USD"),
                    is_active=acct_data.get("is_active", True),
                    created_at=self._parse_datetime(acct_data.get("created_at")),
                    updated_at=self._parse_datetime(acct_data.get("updated_at")),
                )
                self.db.add(account)
                self.db.flush()
                id_map[old_id] = old_id
                result["created"] += 1
            except Exception as e:
                errors.append(f"Failed to restore account {old_id}: {str(e)}")
                result["errors"] += 1

        return id_map, result, errors

    def _restore_rules(
        self,
        user_id: str,
        rules: List[Dict],
        conflict_mode: str
    ) -> tuple[Dict[str, str], Dict[str, int], List[str]]:
        """Restore rules."""
        id_map: Dict[str, str] = {}
        result = {"created": 0, "skipped": 0, "errors": 0}
        errors: List[str] = []

        for rule_data in rules:
            old_id = rule_data.get("id")
            if not old_id:
                errors.append("Rule missing ID")
                result["errors"] += 1
                continue

            existing = self.db.query(Rule).filter(Rule.id == old_id).first()
            if existing:
                if conflict_mode == "error":
                    errors.append(f"Rule {old_id} already exists")
                    result["errors"] += 1
                else:
                    id_map[old_id] = old_id
                    result["skipped"] += 1
                continue

            try:
                rule = Rule(
                    id=old_id,
                    user_id=user_id,
                    rule_type=rule_data.get("rule_type"),
                    pattern=rule_data.get("pattern"),
                    action=rule_data.get("action"),
                    priority=rule_data.get("priority", 0),
                    is_active=rule_data.get("is_active", True),
                    match_count=rule_data.get("match_count", 0),
                    name=rule_data.get("name"),
                    description=rule_data.get("description"),
                    created_at=self._parse_datetime(rule_data.get("created_at")),
                    updated_at=self._parse_datetime(rule_data.get("updated_at")),
                    last_matched_at=self._parse_datetime(rule_data.get("last_matched_at")),
                )
                self.db.add(rule)
                self.db.flush()
                id_map[old_id] = old_id
                result["created"] += 1
            except Exception as e:
                errors.append(f"Failed to restore rule {old_id}: {str(e)}")
                result["errors"] += 1

        return id_map, result, errors

    def _restore_merchant_categories(
        self,
        user_id: str,
        categories: List[Dict],
        conflict_mode: str
    ) -> tuple[Dict[str, int], List[str]]:
        """Restore merchant categories."""
        result = {"created": 0, "skipped": 0, "errors": 0}
        errors: List[str] = []

        for mc_data in categories:
            old_id = mc_data.get("id")
            merchant = mc_data.get("merchant_normalized")

            if not old_id or not merchant:
                errors.append("MerchantCategory missing ID or merchant_normalized")
                result["errors"] += 1
                continue

            # Check by ID first
            existing = self.db.query(MerchantCategory).filter(
                MerchantCategory.id == old_id
            ).first()

            # Also check by unique constraint (user_id, merchant_normalized)
            if not existing:
                existing = self.db.query(MerchantCategory).filter(
                    MerchantCategory.user_id == user_id,
                    MerchantCategory.merchant_normalized == merchant
                ).first()

            if existing:
                if conflict_mode == "error":
                    errors.append(f"MerchantCategory for '{merchant}' already exists")
                    result["errors"] += 1
                else:
                    result["skipped"] += 1
                continue

            try:
                mc = MerchantCategory(
                    id=old_id,
                    user_id=user_id,
                    merchant_normalized=merchant,
                    category=mc_data.get("category"),
                    confidence=mc_data.get("confidence"),
                    source=mc_data.get("source"),
                    times_applied=mc_data.get("times_applied", 0),
                    created_at=self._parse_datetime(mc_data.get("created_at")),
                    updated_at=self._parse_datetime(mc_data.get("updated_at")),
                )
                self.db.add(mc)
                self.db.flush()
                result["created"] += 1
            except Exception as e:
                errors.append(f"Failed to restore merchant category '{merchant}': {str(e)}")
                result["errors"] += 1

        return result, errors

    def _restore_import_records(
        self,
        import_records: List[Dict],
        account_id_map: Dict[str, str],
        conflict_mode: str
    ) -> tuple[Dict[str, str], Dict[str, int], List[str]]:
        """Restore import records."""
        id_map: Dict[str, str] = {}
        result = {"created": 0, "skipped": 0, "errors": 0}
        errors: List[str] = []

        for ir_data in import_records:
            old_id = ir_data.get("id")
            old_account_id = ir_data.get("account_id")

            if not old_id:
                errors.append("ImportRecord missing ID")
                result["errors"] += 1
                continue

            # Map account ID
            new_account_id = account_id_map.get(old_account_id) if old_account_id else None
            if old_account_id and not new_account_id:
                errors.append(f"ImportRecord {old_id}: account {old_account_id} not found")
                result["errors"] += 1
                continue

            existing = self.db.query(ImportRecord).filter(ImportRecord.id == old_id).first()
            if existing:
                if conflict_mode == "error":
                    errors.append(f"ImportRecord {old_id} already exists")
                    result["errors"] += 1
                else:
                    id_map[old_id] = old_id
                    result["skipped"] += 1
                continue

            try:
                ir = ImportRecord(
                    id=old_id,
                    account_id=new_account_id,
                    source_type=ir_data.get("source_type"),
                    filename=ir_data.get("filename"),
                    file_size_bytes=ir_data.get("file_size_bytes"),
                    file_hash=ir_data.get("file_hash"),
                    status=ir_data.get("status"),
                    error_message=ir_data.get("error_message"),
                    transactions_imported=ir_data.get("transactions_imported", 0),
                    transactions_duplicate=ir_data.get("transactions_duplicate", 0),
                    import_metadata=ir_data.get("import_metadata"),
                    created_at=self._parse_datetime(ir_data.get("created_at")),
                    completed_at=self._parse_datetime(ir_data.get("completed_at")),
                )
                self.db.add(ir)
                self.db.flush()
                id_map[old_id] = old_id
                result["created"] += 1
            except Exception as e:
                errors.append(f"Failed to restore import record {old_id}: {str(e)}")
                result["errors"] += 1

        return id_map, result, errors

    def _restore_transactions(
        self,
        transactions: List[Dict],
        account_id_map: Dict[str, str],
        import_id_map: Dict[str, str],
        rule_id_map: Dict[str, str],
        conflict_mode: str
    ) -> tuple[Dict[str, int], List[str]]:
        """Restore transactions."""
        result = {"created": 0, "skipped": 0, "errors": 0}
        errors: List[str] = []

        for txn_data in transactions:
            old_id = txn_data.get("id")
            old_account_id = txn_data.get("account_id")
            hash_key = txn_data.get("hash_dedup_key")

            if not old_id or not old_account_id:
                errors.append("Transaction missing ID or account_id")
                result["errors"] += 1
                continue

            # Map account ID
            new_account_id = account_id_map.get(old_account_id)
            if not new_account_id:
                errors.append(f"Transaction {old_id}: account {old_account_id} not found")
                result["errors"] += 1
                continue

            # Check for existing by ID or hash_dedup_key
            existing = self.db.query(Transaction).filter(Transaction.id == old_id).first()
            if not existing and hash_key:
                existing = self.db.query(Transaction).filter(
                    Transaction.hash_dedup_key == hash_key
                ).first()

            if existing:
                if conflict_mode == "error":
                    errors.append(f"Transaction {old_id} already exists")
                    result["errors"] += 1
                else:
                    result["skipped"] += 1
                continue

            # Map optional foreign keys
            old_import_id = txn_data.get("import_id")
            new_import_id = import_id_map.get(old_import_id) if old_import_id else None

            old_rule_id = txn_data.get("matched_rule_id")
            new_rule_id = rule_id_map.get(old_rule_id) if old_rule_id else None

            try:
                txn = Transaction(
                    id=old_id,
                    account_id=new_account_id,
                    import_id=new_import_id,
                    hash_dedup_key=hash_key,
                    date=self._parse_date(txn_data.get("date")),
                    post_date=self._parse_date(txn_data.get("post_date")),
                    description_raw=txn_data.get("description_raw"),
                    merchant_normalized=txn_data.get("merchant_normalized"),
                    amount=self._parse_decimal(txn_data.get("amount")),
                    currency=txn_data.get("currency", "USD"),
                    transaction_type=txn_data.get("transaction_type"),
                    category=txn_data.get("category"),
                    subcategory=txn_data.get("subcategory"),
                    tags=txn_data.get("tags"),
                    is_spend=txn_data.get("is_spend", True),
                    is_income=txn_data.get("is_income", False),
                    confidence=self._parse_decimal(txn_data.get("confidence")),
                    needs_review=txn_data.get("needs_review", False),
                    reviewed_at=self._parse_datetime(txn_data.get("reviewed_at")),
                    matched_rule_id=new_rule_id,
                    classification_method=txn_data.get("classification_method"),
                    user_note=txn_data.get("user_note"),
                    transaction_metadata=txn_data.get("transaction_metadata"),
                    created_at=self._parse_datetime(txn_data.get("created_at")),
                    updated_at=self._parse_datetime(txn_data.get("updated_at")),
                )
                self.db.add(txn)
                self.db.flush()
                result["created"] += 1
            except Exception as e:
                errors.append(f"Failed to restore transaction {old_id}: {str(e)}")
                result["errors"] += 1

        return result, errors

    def _restore_holdings_snapshots(
        self,
        snapshots: List[Dict],
        account_id_map: Dict[str, str],
        import_id_map: Dict[str, str],
        conflict_mode: str
    ) -> tuple[Dict[str, str], Dict[str, int], List[str]]:
        """Restore holdings snapshots."""
        id_map: Dict[str, str] = {}
        result = {"created": 0, "skipped": 0, "errors": 0}
        errors: List[str] = []

        for hs_data in snapshots:
            old_id = hs_data.get("id")
            old_account_id = hs_data.get("account_id")

            if not old_id or not old_account_id:
                errors.append("HoldingsSnapshot missing ID or account_id")
                result["errors"] += 1
                continue

            new_account_id = account_id_map.get(old_account_id)
            if not new_account_id:
                errors.append(f"HoldingsSnapshot {old_id}: account {old_account_id} not found")
                result["errors"] += 1
                continue

            existing = self.db.query(HoldingsSnapshot).filter(
                HoldingsSnapshot.id == old_id
            ).first()
            if existing:
                if conflict_mode == "error":
                    errors.append(f"HoldingsSnapshot {old_id} already exists")
                    result["errors"] += 1
                else:
                    id_map[old_id] = old_id
                    result["skipped"] += 1
                continue

            old_import_id = hs_data.get("import_id")
            new_import_id = import_id_map.get(old_import_id) if old_import_id else None

            try:
                hs = HoldingsSnapshot(
                    id=old_id,
                    account_id=new_account_id,
                    import_id=new_import_id,
                    statement_date=self._parse_date(hs_data.get("statement_date")),
                    statement_start_date=self._parse_date(hs_data.get("statement_start_date")),
                    total_value=self._parse_decimal(hs_data.get("total_value")),
                    total_cash=self._parse_decimal(hs_data.get("total_cash")),
                    total_securities=self._parse_decimal(hs_data.get("total_securities")),
                    calculated_total=self._parse_decimal(hs_data.get("calculated_total")),
                    is_reconciled=hs_data.get("is_reconciled", False),
                    reconciliation_diff=self._parse_decimal(hs_data.get("reconciliation_diff")),
                    base_currency=hs_data.get("base_currency", "USD"),
                    cash_balances=hs_data.get("cash_balances"),
                    currency=hs_data.get("currency", "USD"),
                    source_file_hash=hs_data.get("source_file_hash"),
                    raw_metadata=hs_data.get("raw_metadata"),
                    created_at=self._parse_datetime(hs_data.get("created_at")),
                )
                self.db.add(hs)
                self.db.flush()
                id_map[old_id] = old_id
                result["created"] += 1
            except Exception as e:
                errors.append(f"Failed to restore holdings snapshot {old_id}: {str(e)}")
                result["errors"] += 1

        return id_map, result, errors

    def _restore_positions(
        self,
        positions: List[Dict],
        snapshot_id_map: Dict[str, str],
        conflict_mode: str
    ) -> tuple[Dict[str, int], List[str]]:
        """Restore positions."""
        result = {"created": 0, "skipped": 0, "errors": 0}
        errors: List[str] = []

        for pos_data in positions:
            old_id = pos_data.get("id")
            old_snapshot_id = pos_data.get("snapshot_id")

            if not old_id or not old_snapshot_id:
                errors.append("Position missing ID or snapshot_id")
                result["errors"] += 1
                continue

            new_snapshot_id = snapshot_id_map.get(old_snapshot_id)
            if not new_snapshot_id:
                errors.append(f"Position {old_id}: snapshot {old_snapshot_id} not found")
                result["errors"] += 1
                continue

            existing = self.db.query(Position).filter(Position.id == old_id).first()
            if existing:
                if conflict_mode == "error":
                    errors.append(f"Position {old_id} already exists")
                    result["errors"] += 1
                else:
                    result["skipped"] += 1
                continue

            try:
                pos = Position(
                    id=old_id,
                    snapshot_id=new_snapshot_id,
                    symbol=pos_data.get("symbol"),
                    cusip=pos_data.get("cusip"),
                    security_name=pos_data.get("security_name"),
                    security_type=pos_data.get("security_type"),
                    quantity=self._parse_decimal(pos_data.get("quantity")),
                    price=self._parse_decimal(pos_data.get("price")),
                    market_value=self._parse_decimal(pos_data.get("market_value")),
                    cost_basis=self._parse_decimal(pos_data.get("cost_basis")),
                    market_value_usd=self._parse_decimal(pos_data.get("market_value_usd")),
                    fx_rate_used=self._parse_decimal(pos_data.get("fx_rate_used")),
                    is_vested=pos_data.get("is_vested", True),
                    vesting_date=self._parse_date(pos_data.get("vesting_date")),
                    asset_class=pos_data.get("asset_class"),
                    currency=pos_data.get("currency", "USD"),
                    row_index=pos_data.get("row_index"),
                )
                self.db.add(pos)
                self.db.flush()
                result["created"] += 1
            except Exception as e:
                errors.append(f"Failed to restore position {old_id}: {str(e)}")
                result["errors"] += 1

        return result, errors

    def _restore_fx_rates(
        self,
        fx_rates: List[Dict],
        snapshot_id_map: Dict[str, str],
        conflict_mode: str
    ) -> tuple[Dict[str, int], List[str]]:
        """Restore FX rates."""
        result = {"created": 0, "skipped": 0, "errors": 0}
        errors: List[str] = []

        for fx_data in fx_rates:
            old_id = fx_data.get("id")
            old_snapshot_id = fx_data.get("snapshot_id")

            if not old_id or not old_snapshot_id:
                errors.append("FxRate missing ID or snapshot_id")
                result["errors"] += 1
                continue

            new_snapshot_id = snapshot_id_map.get(old_snapshot_id)
            if not new_snapshot_id:
                errors.append(f"FxRate {old_id}: snapshot {old_snapshot_id} not found")
                result["errors"] += 1
                continue

            existing = self.db.query(FxRate).filter(FxRate.id == old_id).first()
            if existing:
                if conflict_mode == "error":
                    errors.append(f"FxRate {old_id} already exists")
                    result["errors"] += 1
                else:
                    result["skipped"] += 1
                continue

            try:
                fx = FxRate(
                    id=old_id,
                    snapshot_id=new_snapshot_id,
                    from_currency=fx_data.get("from_currency"),
                    to_currency=fx_data.get("to_currency"),
                    rate=self._parse_decimal(fx_data.get("rate")),
                    rate_date=self._parse_date(fx_data.get("rate_date")),
                    source=fx_data.get("source"),
                )
                self.db.add(fx)
                self.db.flush()
                result["created"] += 1
            except Exception as e:
                errors.append(f"Failed to restore FX rate {old_id}: {str(e)}")
                result["errors"] += 1

        return result, errors
