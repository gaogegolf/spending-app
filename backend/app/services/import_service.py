"""Import orchestration service - coordinates file upload, parsing, classification, and database import."""

import os
import hashlib
import shutil
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from sqlalchemy.orm import Session
from fastapi import UploadFile

from app.models.import_record import ImportRecord, SourceType, ImportStatus
from app.models.transaction import Transaction
from app.models.account import Account
from app.services.file_parser.csv_parser import CSVParser
from app.services.file_parser.pdf_parser import PDFParser
from app.services.classifier.llm_classifier import LLMClassifier
from app.services.classifier.rule_engine import RuleEngine
from app.services.deduplication import DeduplicationService
from app.config import settings


class ImportService:
    """Service to orchestrate the import process."""

    def __init__(self, db: Session):
        """Initialize import service.

        Args:
            db: Database session
        """
        self.db = db
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.llm_classifier = LLMClassifier()
        self.rule_engine = RuleEngine(db)
        self.dedup_service = DeduplicationService(db)

    async def process_upload(
        self,
        file: UploadFile,
        account_id: str
    ) -> ImportRecord:
        """Process file upload and create import record.

        Args:
            file: Uploaded file
            account_id: Account ID to associate with import

        Returns:
            ImportRecord with PENDING status
        """
        # Validate account exists
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise ValueError(f"Account {account_id} not found")

        # Determine source type
        filename = file.filename
        if filename.lower().endswith('.csv'):
            source_type = SourceType.CSV
        elif filename.lower().endswith('.pdf'):
            source_type = SourceType.PDF
        else:
            raise ValueError(f"Unsupported file type: {filename}")

        # Calculate file hash for deduplication
        file_content = await file.read()
        file_hash = hashlib.sha256(file_content).hexdigest()
        await file.seek(0)  # Reset file pointer

        # Check if this file was already imported
        existing = self.db.query(ImportRecord).filter(
            ImportRecord.account_id == account_id,
            ImportRecord.file_hash == file_hash
        ).first()

        if existing:
            raise ValueError(
                f"This file was already imported on {existing.created_at}. "
                f"Import ID: {existing.id}"
            )

        # Save file to disk
        import_record = ImportRecord(
            account_id=account_id,
            source_type=source_type,
            filename=filename,
            file_size_bytes=len(file_content),
            file_hash=file_hash,
            status=ImportStatus.PENDING
        )

        self.db.add(import_record)
        self.db.commit()
        self.db.refresh(import_record)

        # Save uploaded file
        file_path = self.upload_dir / f"{import_record.id}_{filename}"
        with open(file_path, 'wb') as f:
            f.write(file_content)

        return import_record

    async def parse_file(
        self,
        import_id: str,
        column_mapping: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Parse uploaded file and return preview.

        Args:
            import_id: Import record ID
            column_mapping: Optional user-provided column mapping for CSV

        Returns:
            Preview dict with transactions, detected columns, etc.
        """
        import_record = self.db.query(ImportRecord).filter(
            ImportRecord.id == import_id
        ).first()

        if not import_record:
            raise ValueError(f"Import record {import_id} not found")

        if import_record.status not in [ImportStatus.PENDING, ImportStatus.PROCESSING]:
            raise ValueError(
                f"Import {import_id} has already been processed (status: {import_record.status})"
            )

        # Update status to PROCESSING
        import_record.status = ImportStatus.PROCESSING
        self.db.commit()

        try:
            # Find uploaded file
            file_path = self._get_file_path(import_record)

            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            # Parse based on source type
            if import_record.source_type == SourceType.CSV:
                parser = CSVParser(str(file_path))
                result = parser.parse()

                # If column mapping provided, apply it
                if column_mapping:
                    # Re-parse with column mapping
                    # TODO: Implement column mapping logic in CSVParser
                    pass

                detected_columns = parser.detect_format() if not column_mapping else None

            elif import_record.source_type == SourceType.PDF:
                parser = PDFParser(str(file_path))
                result = parser.parse()
                detected_columns = None

            else:
                raise ValueError(f"Unsupported source type: {import_record.source_type}")

            if not result.success:
                import_record.status = ImportStatus.FAILED
                import_record.error_message = "; ".join(result.errors)
                self.db.commit()

                return {
                    'success': False,
                    'errors': result.errors,
                    'warnings': result.warnings
                }

            # Store parsed transactions in import_metadata for later commit
            import_record.import_metadata = {
                'parsed_transactions': result.transactions,
                'detected_columns': detected_columns,
                'parse_metadata': result.metadata
            }

            self.db.commit()

            # Run deduplication check (preview only, don't skip yet)
            duplicate_hashes = self.dedup_service.check_duplicates(
                account_id=import_record.account_id,
                transactions=result.transactions
            )

            duplicate_count = len(duplicate_hashes)

            return {
                'success': True,
                'import_id': import_id,
                'filename': import_record.filename,
                'source_type': import_record.source_type.value,
                'detected_columns': detected_columns,
                'transactions_preview': result.transactions[:20],  # First 20 for preview
                'total_count': len(result.transactions),
                'duplicate_count': duplicate_count,
                'warnings': result.warnings
            }

        except Exception as e:
            import_record.status = ImportStatus.FAILED
            import_record.error_message = str(e)
            self.db.commit()
            raise

    async def commit_import(self, import_id: str) -> ImportRecord:
        """Finalize import - classify and insert transactions into database.

        Args:
            import_id: Import record ID

        Returns:
            Updated import record with SUCCESS/PARTIAL/FAILED status
        """
        import_record = self.db.query(ImportRecord).filter(
            ImportRecord.id == import_id
        ).first()

        if not import_record:
            raise ValueError(f"Import record {import_id} not found")

        if import_record.status != ImportStatus.PROCESSING:
            raise ValueError(
                f"Import {import_id} cannot be committed (status: {import_record.status})"
            )

        if not import_record.import_metadata or 'parsed_transactions' not in import_record.import_metadata:
            raise ValueError(
                f"Import {import_id} has no parsed transactions. Call parse_file() first."
            )

        try:
            parsed_txns = import_record.import_metadata['parsed_transactions']

            # Step 1: Deduplication - filter out existing transactions
            new_txns = self.dedup_service.filter_duplicates(
                account_id=import_record.account_id,
                transactions=parsed_txns
            )

            duplicate_count = len(parsed_txns) - len(new_txns)

            if not new_txns:
                import_record.status = ImportStatus.SUCCESS
                import_record.transactions_imported = 0
                import_record.transactions_duplicate = duplicate_count
                import_record.completed_at = datetime.utcnow()
                self.db.commit()
                return import_record

            # Step 2: Apply user rules first
            rule_matched_txns = []
            unmatched_txns = []

            for txn_data in new_txns:
                matched_rule = self.rule_engine.match_transaction_data(txn_data)

                if matched_rule:
                    classified_txn = self.rule_engine.apply_rule_to_data(
                        matched_rule,
                        txn_data
                    )
                    rule_matched_txns.append(classified_txn)
                else:
                    unmatched_txns.append(txn_data)

            # Step 3: Send unmatched to LLM classifier
            llm_classified_txns = []

            if unmatched_txns and settings.ENABLE_LLM_CLASSIFICATION:
                classified_results = self.llm_classifier.classify_batch(unmatched_txns)
                llm_classified_txns = classified_results
            else:
                # If LLM disabled, use default classification
                llm_classified_txns = [
                    self._default_classification(txn) for txn in unmatched_txns
                ]

            # Step 4: Merge original transaction data with classifications and insert
            all_classified = rule_matched_txns + llm_classified_txns

            for i, classified_data in enumerate(all_classified):
                # Get the original transaction data
                original_txn = new_txns[i] if i < len(new_txns) else {}

                # Merge original transaction data with classification
                # Original data has: date, amount, description_raw, merchant_normalized, currency, is_credit
                # Classification has: transaction_type, category, subcategory, is_spend, is_income, etc.
                merged_data = {
                    **original_txn,  # Start with original data
                    **classified_data  # Override/add classification fields
                }

                # Remove is_credit field (not part of Transaction model)
                merged_data.pop('is_credit', None)

                # Convert date from string to date object if needed
                if 'date' in merged_data and isinstance(merged_data['date'], str):
                    from datetime import datetime
                    merged_data['date'] = datetime.fromisoformat(merged_data['date']).date()

                if 'post_date' in merged_data and isinstance(merged_data['post_date'], str):
                    from datetime import datetime
                    merged_data['post_date'] = datetime.fromisoformat(merged_data['post_date']).date()

                transaction = Transaction(
                    account_id=import_record.account_id,
                    import_id=import_record.id,
                    hash_dedup_key=self.dedup_service.generate_hash(import_record.account_id, original_txn),
                    **merged_data
                )

                # Ensure is_spend and is_income are set based on transaction_type
                transaction.set_is_spend_based_on_type()

                self.db.add(transaction)

            self.db.commit()

            # Update import record
            import_record.status = ImportStatus.SUCCESS
            import_record.transactions_imported = len(all_classified)
            import_record.transactions_duplicate = duplicate_count
            import_record.completed_at = datetime.utcnow()
            self.db.commit()

            return import_record

        except Exception as e:
            import_record.status = ImportStatus.FAILED
            import_record.error_message = str(e)
            self.db.commit()
            raise

    def _get_file_path(self, import_record: ImportRecord) -> Path:
        """Get file path for import record."""
        return self.upload_dir / f"{import_record.id}_{import_record.filename}"

    def _default_classification(self, txn_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply default classification when LLM is disabled."""
        description = txn_data.get('description_raw', '').upper()

        # Simple keyword-based classification
        if any(keyword in description for keyword in ['PAYMENT', 'AUTOPAY', 'THANK YOU']):
            txn_type = 'PAYMENT'
            is_spend = False
            is_income = False
        elif any(keyword in description for keyword in ['SALARY', 'PAYROLL', 'DEPOSIT']):
            txn_type = 'INCOME'
            is_spend = False
            is_income = True
        elif any(keyword in description for keyword in ['TRANSFER', 'ZELLE', 'VENMO']):
            txn_type = 'TRANSFER'
            is_spend = False
            is_income = False
        elif any(keyword in description for keyword in ['REFUND', 'RETURN', 'REVERSAL']):
            txn_type = 'REFUND'
            is_spend = False
            is_income = False
        else:
            # Default to EXPENSE
            txn_type = 'EXPENSE'
            is_spend = True
            is_income = False

        return {
            **txn_data,
            'transaction_type': txn_type,
            'category': 'Uncategorized',
            'is_spend': is_spend,
            'is_income': is_income,
            'classification_method': 'DEFAULT',
            'confidence': 0.5,
            'needs_review': True
        }

    async def delete_import(self, import_id: str) -> None:
        """Delete an import record and its uploaded file.

        Args:
            import_id: Import record ID
        """
        import_record = self.db.query(ImportRecord).filter(
            ImportRecord.id == import_id
        ).first()

        if not import_record:
            raise ValueError(f"Import record {import_id} not found")

        # Delete uploaded file
        file_path = self._get_file_path(import_record)
        if file_path.exists():
            file_path.unlink()

        # Delete from database (cascade will delete associated transactions)
        self.db.delete(import_record)
        self.db.commit()
