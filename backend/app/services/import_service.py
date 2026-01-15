"""Import orchestration service - coordinates file upload, parsing, classification, and database import."""

import os
import hashlib
import shutil
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from sqlalchemy.orm import Session
from fastapi import UploadFile

logger = logging.getLogger(__name__)

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

        # Check if this file was already imported (warn but allow re-import)
        existing = self.db.query(ImportRecord).filter(
            ImportRecord.account_id == account_id,
            ImportRecord.file_hash == file_hash
        ).first()

        if existing:
            logger.warning(
                f"File was previously imported on {existing.created_at}. "
                f"Import ID: {existing.id}. Allowing re-import."
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
                file_hash=import_record.file_hash,
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
            file_hash = import_record.file_hash

            # Step 1: Deduplication - filter out existing transactions
            new_txns = self.dedup_service.filter_duplicates(
                account_id=import_record.account_id,
                file_hash=file_hash,
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

            # Step 3: Check learned merchant categories first
            learned_txns = []
            still_unmatched = []

            for txn in unmatched_txns:
                merchant_normalized = txn.get('merchant_normalized', '')
                if merchant_normalized:
                    from app.models.merchant_category import MerchantCategory
                    learned = self.db.query(MerchantCategory).filter(
                        MerchantCategory.user_id == 'default_user',
                        MerchantCategory.merchant_normalized == merchant_normalized
                    ).first()

                    if learned:
                        # Apply learned category
                        learned.times_applied += 1
                        amount = float(txn.get('amount', 0))

                        # Negative amounts = INCOME (refunds/credits)
                        # Positive amounts = EXPENSE
                        if amount < 0:
                            learned_txns.append({
                                **txn,
                                'transaction_type': 'INCOME',
                                'category': learned.category,
                                'is_spend': False,
                                'is_income': True,
                                'classification_method': 'LEARNED',
                                'confidence': learned.confidence,
                                'needs_review': False
                            })
                        else:
                            learned_txns.append({
                                **txn,
                                'transaction_type': 'EXPENSE',
                                'category': learned.category,
                                'is_spend': True,
                                'is_income': False,
                                'classification_method': 'LEARNED',
                                'confidence': learned.confidence,
                                'needs_review': False
                            })
                        continue

                still_unmatched.append(txn)

            # Step 4: Send remaining unmatched to LLM classifier
            llm_classified_txns = []

            if still_unmatched and settings.ENABLE_LLM_CLASSIFICATION:
                classified_results = self.llm_classifier.classify_batch(still_unmatched)
                # CRITICAL: Merge classification results with original transaction data
                # The LLM classifier only returns classification fields, not the original
                # transaction data (date, amount, row_index, etc.)
                for j, classification in enumerate(classified_results):
                    if j < len(still_unmatched):
                        llm_classified_txns.append({**still_unmatched[j], **classification})
                    else:
                        llm_classified_txns.append(classification)
            else:
                # If LLM disabled, use default classification
                # Also merge with original transaction data
                llm_classified_txns = [
                    {**txn, **self._default_classification(txn)} for txn in still_unmatched
                ]

            # Step 5: Merge all classified transactions and insert
            all_classified = rule_matched_txns + learned_txns + llm_classified_txns

            successfully_inserted = 0
            duplicate_count = 0
            seen_hashes = set()  # Track hashes within this batch to avoid within-batch duplicates

            for classified_data in all_classified:
                # Each classified_data now contains the original transaction data
                # (rule_matched uses txn_data.copy(), learned uses **txn, llm now merges too)
                # No need to look up new_txns[i] - indices wouldn't match anyway since
                # all_classified = rule_matched + learned + llm, which are built from
                # different subsets of new_txns

                # Generate hash for deduplication using file_hash + row_index
                txn_hash = self.dedup_service.generate_hash(import_record.account_id, file_hash, classified_data)

                # Check for duplicates in database
                existing = self.db.query(Transaction).filter(
                    Transaction.hash_dedup_key == txn_hash
                ).first()

                if existing:
                    logger.info(f"Skipping duplicate transaction (already in DB): {classified_data.get('description_raw', 'Unknown')}")
                    duplicate_count += 1
                    continue

                # Check for duplicates within current batch
                if txn_hash in seen_hashes:
                    logger.info(f"Skipping duplicate transaction (within batch): {classified_data.get('description_raw', 'Unknown')}")
                    duplicate_count += 1
                    continue

                # classified_data already contains both original transaction data and classification
                # Original data has: date, amount, description_raw, merchant_normalized, currency, is_credit, row_index
                # Classification has: transaction_type, category, subcategory, is_spend, is_income, etc.
                merged_data = classified_data.copy()

                # Remove fields not part of Transaction model
                merged_data.pop('is_credit', None)  # Legacy field
                merged_data.pop('is_payment', None)  # Used for classification only
                merged_data.pop('row_index', None)  # Used for deduplication only, not stored
                merged_data.pop('metadata', None)  # CSV metadata, not directly stored

                # Convert date from string to date object if needed
                if 'date' in merged_data and isinstance(merged_data['date'], str):
                    merged_data['date'] = datetime.fromisoformat(merged_data['date']).date()

                if 'post_date' in merged_data and isinstance(merged_data['post_date'], str):
                    merged_data['post_date'] = datetime.fromisoformat(merged_data['post_date']).date()

                transaction = Transaction(
                    account_id=import_record.account_id,
                    import_id=import_record.id,
                    hash_dedup_key=txn_hash,
                    **merged_data
                )

                # Ensure is_spend and is_income are set based on transaction_type
                transaction.set_is_spend_based_on_type()

                # Insert immediately with error handling
                try:
                    self.db.add(transaction)
                    self.db.flush()  # Flush to detect constraint violations immediately
                    seen_hashes.add(txn_hash)  # Mark as seen after successful flush
                    successfully_inserted += 1
                except Exception as e:
                    logger.warning(f"Failed to insert transaction (constraint violation): {str(e)}")
                    self.db.rollback()  # Rollback to recover from error
                    duplicate_count += 1

            self.db.commit()

            # Update import record
            import_record.status = ImportStatus.SUCCESS
            import_record.transactions_imported = successfully_inserted
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
        """Apply default classification when LLM is disabled or fails.

        Priority order:
        1. Check for payment flag (credit card payments are transfers)
        2. Check learned merchant categories (user corrections)
        3. Check for negative amounts (refunds/credits = INCOME)
        4. Apply keyword-based rules for transaction types
        5. Use merchant pattern matching for categories

        IMPORTANT: Negative amounts in credit card statements represent refunds/credits
        and should be classified as INCOME, not EXPENSE.
        """
        from app.models.merchant_category import MerchantCategory

        description = txn_data.get('description_raw', '').upper()
        merchant_normalized = txn_data.get('merchant_normalized', '')
        amount = float(txn_data.get('amount', 0))
        is_payment = txn_data.get('is_payment', False)

        # Priority 0: Check if this is a payment to the credit card (transfer)
        if is_payment:
            return {
                **txn_data,
                'transaction_type': 'TRANSFER',
                'category': 'Credit Card Payments',
                'is_spend': False,
                'is_income': False,
                'classification_method': 'DEFAULT',
                'confidence': 0.9,
                'needs_review': False
            }

        # Priority 1: Check if we've learned a category for this merchant
        if merchant_normalized:
            learned = self.db.query(MerchantCategory).filter(
                MerchantCategory.user_id == 'default_user',
                MerchantCategory.merchant_normalized == merchant_normalized
            ).first()

            if learned:
                # Apply learned category and increment usage counter
                learned.times_applied += 1
                self.db.flush()  # Update counter immediately

                # Negative amounts = INCOME (refunds/credits)
                # Positive amounts = EXPENSE
                if amount < 0:
                    return {
                        **txn_data,
                        'transaction_type': 'INCOME',
                        'category': learned.category,
                        'is_spend': False,
                        'is_income': True,
                        'classification_method': 'LEARNED',
                        'confidence': learned.confidence,
                        'needs_review': False
                    }
                else:
                    return {
                        **txn_data,
                        'transaction_type': 'EXPENSE',
                        'category': learned.category,
                        'is_spend': True,
                        'is_income': False,
                        'classification_method': 'LEARNED',
                        'confidence': learned.confidence,
                        'needs_review': False
                    }

        # Priority 2: Determine transaction type from keywords and amount
        # Check for payments/transfers first
        if any(keyword in description for keyword in ['PAYMENT', 'AUTOPAY', 'THANK YOU']):
            txn_type = 'TRANSFER'
            is_spend = False
            is_income = False
            category = 'Credit Card Payments'
        elif any(keyword in description for keyword in ['SALARY', 'PAYROLL', 'DEPOSIT', 'DIRECT DEP']):
            txn_type = 'INCOME'
            is_spend = False
            is_income = True
            category = 'Paychecks/Salary'
        elif any(keyword in description for keyword in ['TRANSFER', 'ZELLE', 'VENMO', 'CASHOUT']):
            txn_type = 'TRANSFER'
            is_spend = False
            is_income = False
            category = 'Transfers'
        elif amount < 0:
            # NEGATIVE AMOUNTS = Refunds/Credits = INCOME
            # This includes merchant refunds, card benefit credits, returned purchases
            txn_type = 'INCOME'
            is_spend = False
            is_income = True
            # Try to categorize based on description
            if any(keyword in description for keyword in ['REFUND', 'RETURN', 'REVERSAL', 'MERCHANDISE/SERVICE RETURN']):
                category = 'Refunds & Reimbursements'
            elif any(keyword in description for keyword in ['CREDIT', 'REIMBURSEMENT', 'CASHBACK']):
                category = 'Refunds & Reimbursements'
            else:
                # Use merchant-based category for better tracking
                category = self._categorize_by_merchant(description)
                if category == 'Other Expenses':
                    category = 'Refunds & Reimbursements'
        elif any(keyword in description for keyword in ['REFUND', 'RETURN', 'REVERSAL', 'MERCHANDISE/SERVICE RETURN']):
            # Explicit refund keywords even with positive amount (edge case)
            txn_type = 'INCOME'
            is_spend = False
            is_income = True
            category = 'Refunds & Reimbursements'
        elif any(keyword in description for keyword in ['LATE FEE', 'ANNUAL FEE', 'OVERDRAFT', 'INTEREST CHARGE', 'MEMBERSHIP FEE']):
            txn_type = 'EXPENSE'
            is_spend = True
            is_income = False
            category = 'Service Charges/Fees'
        else:
            # Positive amount = EXPENSE
            txn_type = 'EXPENSE'
            is_spend = True
            is_income = False

            # Try to categorize by merchant patterns
            category = self._categorize_by_merchant(description)
            if not category:
                category = 'Other Expenses'

        return {
            **txn_data,
            'transaction_type': txn_type,
            'category': category,
            'is_spend': is_spend,
            'is_income': is_income,
            'classification_method': 'DEFAULT',
            'confidence': 0.7,
            'needs_review': False
        }

    def _categorize_by_merchant(self, description: str) -> str:
        """Categorize transaction based on merchant name patterns using Empower categories.

        Args:
            description: Transaction description (should be uppercase)

        Returns:
            Category name
        """
        # Restaurants (most specific food category)
        restaurant_keywords = ['RESTAURANT', 'CAFE', 'COFFEE', 'STARBUCKS', 'MCDONALDS', 'BURGER', 'PIZZA',
                              'CHIPOTLE', 'PANERA', 'SUBWAY', 'DOORDASH', 'UBER EATS', 'GRUBHUB', 'POSTMATES',
                              'DINING', 'KITCHEN', 'BISTRO', 'GRILL', 'SUSHI', 'BAR', 'LUNCH', 'BREAKFAST',
                              'WENDYS', 'TACO BELL', 'KFC', 'ARBYS', 'DOMINO', 'DINER', 'BUFFET',
                              'CHILI', 'RAMEN', 'MANDARIN', 'CUISINE', 'CREPEVINE', 'PANDA EXPRESS',
                              'IN-N-OUT', 'FIVE GUYS', 'SHAKE SHACK', 'OLIVE GARDEN', 'APPLEBEES',
                              'OUTBACK', 'TEXAS ROADHOUSE', 'CHEESECAKE FACTORY', 'PF CHANG',
                              'BENIHANA', 'BOBA', 'TEA HOUSE', 'POKE', 'TAQUERIA', 'BBQ', 'STEAKHOUSE',
                              'SQ *', 'PY *', 'NUTRITION']  # Square & PayPal payments often restaurants
        if any(kw in description for kw in restaurant_keywords):
            return 'Restaurants'

        # Groceries (separate from restaurants)
        grocery_keywords = ['WHOLE FOODS', 'SAFEWAY', 'TRADER JOE', 'GROCERY', 'MARKET', 'KROGER',
                           'ALBERTSONS', 'FOOD LION', 'PUBLIX', 'WEGMANS', 'HEB', 'ALDI', 'COSTCO',
                           'SAMS CLUB', 'SUPERMARKET', 'FRESH', 'PRODUCE', 'WEEE', 'FOODLAND',
                           'FARMERS MARKET', 'ASIAN MARKET', 'RANCH 99', '99 RANCH']
        if any(kw in description for kw in grocery_keywords):
            return 'Groceries'

        # Gasoline/Fuel (specific category)
        fuel_keywords = ['SHELL', 'CHEVRON', 'MOBIL', 'EXXON', 'BP ', 'ARCO', 'VALERO', '76', 'MARATHON',
                        'GAS STATION', 'FUEL', 'PETRO', 'CIRCLE K', 'SPEEDWAY', 'PILOT', 'FLYING J']
        if any(kw in description for kw in fuel_keywords):
            return 'Gasoline/Fuel'

        # Automotive (car-related but not fuel)
        automotive_keywords = ['AUTO', 'CAR WASH', 'JIFFY LUBE', 'MIDAS', 'TIRE', 'BRAKE', 'MEINEKE',
                              'PEP BOYS', 'AUTOZONE', 'NAPA', 'O REILLY', 'CAR PARTS', 'MECHANIC',
                              'SMOG', 'REGISTRATION', 'DMV', 'PARKING', 'GARAGE', 'CHARGEPOINT',
                              'CARFAX', 'CALTRAIN', 'TRANSIT', 'TRAIN', 'METRO', 'BUS', 'BART',
                              'TOLL', 'FASTRAK', 'EZ PASS']
        if any(kw in description for kw in automotive_keywords):
            return 'Automotive'

        # Travel (hotels, airlines, etc.)
        travel_keywords = ['AIRLINE', 'AIRWAYS', 'UNITED', 'DELTA', 'AMERICAN AIR', 'SOUTHWEST', 'JETBLUE',
                          'HOTEL', 'MARRIOTT', 'HILTON', 'HYATT', 'AIRBNB', 'EXPEDIA', 'BOOKING.COM',
                          'TRAVEL', 'TRIP', 'VACATION', 'RESORT', 'INN', 'MOTEL', 'RENTAL CAR',
                          'HERTZ', 'ENTERPRISE', 'AVIS', 'BUDGET']
        if any(kw in description for kw in travel_keywords):
            return 'Travel'

        # Utilities
        utilities_keywords = ['PG&E', 'EDISON', 'ELECTRIC', 'GAS COMPANY', 'WATER DISTRICT', 'UTILITY',
                             'POWER', 'ENERGY', 'WATER BILL', 'SEWER', 'WASTE MANAGEMENT', 'TRASH']
        if any(kw in description for kw in utilities_keywords):
            return 'Utilities'

        # Cable/Satellite & Internet
        cable_keywords = ['COMCAST', 'XFINITY', 'SPECTRUM', 'COX', 'FRONTIER', 'CENTURYLINK',
                         'DIRECTV', 'DISH NETWORK', 'CABLE', 'INTERNET', 'BROADBAND', 'FIBER']
        if any(kw in description for kw in cable_keywords):
            return 'Cable/Satellite'

        # Telephone
        phone_keywords = ['VERIZON', 'AT&T', 'T-MOBILE', 'SPRINT', 'PHONE', 'WIRELESS', 'CELLULAR',
                         'MOBILE', 'CRICKET', 'METRO PCS', 'BOOST MOBILE']
        if any(kw in description for kw in phone_keywords):
            return 'Telephone'

        # Healthcare/Medical
        healthcare_keywords = ['CVS', 'WALGREENS', 'RITE AID', 'PHARMACY', 'KAISER', 'BLUE SHIELD',
                              'DOCTOR', 'DENTAL', 'DENTIST', 'MEDICAL', 'HOSPITAL', 'CLINIC',
                              'OPTOMETRY', 'VISION', 'HEALTH', 'URGENT CARE', 'LABS', 'IMAGING']
        if any(kw in description for kw in healthcare_keywords):
            return 'Healthcare/Medical'

        # Insurance
        insurance_keywords = ['INSURANCE', 'GEICO', 'STATE FARM', 'ALLSTATE', 'PROGRESSIVE', 'LIBERTY MUTUAL',
                             'FARMERS INS', 'USAA', 'AAA', 'POLICY', 'PREMIUM']
        if any(kw in description for kw in insurance_keywords):
            return 'Insurance'

        # Personal Care
        personal_keywords = ['GYM', 'FITNESS', '24 HOUR', 'LA FITNESS', 'PLANET FITNESS', 'EQUINOX',
                            'SALON', 'BARBER', 'SPA', 'MASSAGE', 'SEPHORA', 'ULTA', 'BEAUTY',
                            'NAILS', 'HAIRCUT', 'YOGA', 'CROSSFIT']
        if any(kw in description for kw in personal_keywords):
            return 'Personal Care'

        # Entertainment
        entertainment_keywords = ['NETFLIX', 'HULU', 'DISNEY', 'HBO', 'SPOTIFY', 'APPLE MUSIC',
                                 'YOUTUBE', 'TWITCH', 'THEATER', 'CINEMA', 'MOVIE', 'AMC', 'REGAL',
                                 'PLAYSTATION', 'XBOX', 'NINTENDO', 'STEAM', 'GAME', 'CONCERT',
                                 'TICKETMASTER', 'STUBHUB', 'AQUARIUM', 'MUSEUM', 'ZOO', 'AMUSEMENT',
                                 'THEME PARK', 'CHUCK E CHEESE', 'DAVE AND BUSTER', 'BOWL', 'ARCADE',
                                 'WINERY', 'VINEYARD', 'SCENIC', 'CURIODYSSEY', 'MONTEREY BAY']
        if any(kw in description for kw in entertainment_keywords):
            return 'Entertainment'

        # Dues & Subscriptions
        subscription_keywords = ['ADOBE', 'MICROSOFT 365', 'OFFICE 365', 'ICLOUD', 'DROPBOX',
                                'GITHUB', 'LINKEDIN', 'PATREON', 'SUBSTACK', 'SUBSCRIPTION',
                                'MEMBERSHIP', 'ANNUAL FEE', 'MONTHLY FEE']
        if any(kw in description for kw in subscription_keywords):
            return 'Dues & Subscriptions'

        # Home Improvement
        home_improvement_keywords = ['HOME DEPOT', 'LOWES', 'ACE HARDWARE', 'MENARDS', 'TRUE VALUE',
                                    'HARDWARE', 'LUMBER', 'CONSTRUCTION', 'REMODEL', 'RENOVATION',
                                    'SOLAR', 'PANEL', 'ROOFING']
        if any(kw in description for kw in home_improvement_keywords):
            return 'Home Improvement'

        # Home Maintenance
        home_maintenance_keywords = ['PLUMBER', 'ELECTRICIAN', 'CONTRACTOR', 'REPAIR', 'MAINTENANCE',
                                    'HVAC', 'HEATING', 'COOLING', 'ROOFING', 'PAINTING', 'CLEANING',
                                    'LAWN', 'GARDEN', 'LANDSCAPE', 'MAID', 'HANDYMAN']
        if any(kw in description for kw in home_maintenance_keywords):
            return 'Home Maintenance'

        # Pets/Pet Care
        pet_keywords = ['PETCO', 'PETSMART', 'VET', 'VETERINARY', 'PET', 'ANIMAL HOSPITAL',
                       'DOG', 'CAT', 'GROOMING']
        if any(kw in description for kw in pet_keywords):
            return 'Pets/Pet Care'

        # Education
        education_keywords = ['UNIVERSITY', 'COLLEGE', 'SCHOOL', 'TUITION', 'COURSERA', 'UDEMY',
                             'EDUCATION', 'LEARNING', 'TEXTBOOK', 'HOMEROOM', 'ACADEMY', 'INSTITUTE',
                             'BOOKSTORE', 'BOOKS', 'LINDEN TREE']
        if any(kw in description for kw in education_keywords):
            return 'Education'

        # Electronics
        electronics_keywords = ['BEST BUY', 'APPLE STORE', 'MICROSOFT STORE', 'ELECTRONICS', 'COMPUTER',
                               'LAPTOP', 'PHONE STORE', 'TECH', 'GEEK SQUAD', 'MICRO CENTER']
        if any(kw in description for kw in electronics_keywords):
            return 'Electronics'

        # Clothing/Shoes
        clothing_keywords = ['MACYS', 'NORDSTROM', 'KOHLS', 'GAP ', 'OLD NAVY', 'BANANA REPUBLIC',
                            'FOREVER 21', 'H&M', ' HM ', 'ZARA', 'NIKE', 'ADIDAS', 'CLOTHING', 'APPAREL',
                            'SHOES', 'FOOTWEAR', 'FASHION', 'UNIQLO', 'CROCS', 'JEANS', 'VANS',
                            'CONVERSE', 'SKECHERS', 'DRESS', 'SUIT', 'TUXEDO', 'DILLARD', 'BLOOMINGDALE',
                            'NEIMAN MARCUS', 'SAKS', 'JCPENNEY', 'NORDSTROM RACK', 'OFF 5TH',
                            'ATHLETIC', 'FOOTLOCKER', 'FINISH LINE', 'DICK SPORTING', 'REI']
        if any(kw in description for kw in clothing_keywords):
            return 'Clothing/Shoes'

        # Charitable Giving
        charity_keywords = ['DONATION', 'CHARITY', 'FOUNDATION', 'NON-PROFIT', 'GOODWILL',
                           'SALVATION ARMY', 'RED CROSS', 'UNITED WAY', 'GIVING']
        if any(kw in description for kw in charity_keywords):
            return 'Charitable Giving'

        # Gifts
        gift_keywords = ['GIFT', 'FLOWERS', 'FLORIST', '1-800-FLOWERS', 'EDIBLE ARRANGEMENTS',
                        'HALLMARK', 'CARD STORE']
        if any(kw in description for kw in gift_keywords):
            return 'Gifts'

        # Hobbies
        hobby_keywords = ['HOBBY', 'CRAFT', 'MICHAELS', 'JOANN', 'FABRIC', 'ART SUPPLY',
                         'MUSIC STORE', 'INSTRUMENT', 'SPORTING GOODS', 'BICYCLE', 'BIKE SHOP',
                         'SPORTS', 'TENNIS', 'GOLF', 'SWIM']
        if any(kw in description for kw in hobby_keywords):
            return 'Hobbies'

        # Online Services
        online_keywords = ['PAYPAL', 'VENMO', 'SQUARE', 'STRIPE', 'ONLINE', 'DIGITAL', 'CLOUD',
                          'HOSTING', 'DOMAIN', 'WEB']
        if any(kw in description for kw in online_keywords):
            return 'Online Services'

        # Taxes
        tax_keywords = ['TAX BOARD', 'FRANCHISE TAX', 'IRS', 'TAX PAYMENT', 'PROPERTY TAX',
                       'INCOME TAX', 'STATE TAX', 'FEDERAL TAX', 'TAX RETURN', 'US TREAS TAX']
        if any(kw in description for kw in tax_keywords):
            return 'Taxes'

        # ATM/Cash
        atm_keywords = ['ATM', 'CASH WITHDRAWAL', 'CASH ADVANCE', 'WITHDRAW']
        if any(kw in description for kw in atm_keywords):
            return 'ATM/Cash'

        # Groceries (additional patterns - check again for meat/butcher shops & convenience stores)
        grocery_keywords2 = ['MEAT HOUSE', 'BUTCHER', 'SEAFOOD', 'FISH MARKET', '7-ELEVEN', '7 ELEVEN',
                            'CONVENIENCE', 'CORNER STORE', 'MINI MART', 'ABC STORE', 'ABC #']
        if any(kw in description for kw in grocery_keywords2):
            return 'Groceries'

        # Pets/Pet Care (additional patterns)
        pet_keywords2 = ['CHEWY', 'PET SUPPLIES', 'PET FOOD']
        if any(kw in description for kw in pet_keywords2):
            return 'Pets/Pet Care'

        # Travel (additional patterns - cruise lines, vacation packages, scenic drives)
        travel_keywords2 = ['CRUISE', 'DCL', 'CARNIVAL', 'ROYAL CARIBBEAN', 'NORWEGIAN',
                           'PRINCESS CRUISES', 'VACATION PACKAGE', '17 MILE DRIVE', 'SCENIC DRIVE',
                           'GATES', 'RESERVATIONS']
        if any(kw in description for kw in travel_keywords2):
            return 'Travel'

        # General Merchandise (big box stores)
        general_merchandise_keywords = ['AMAZON', 'TARGET', 'WALMART', 'COSTCO', 'SAMS CLUB',
                                       'BJS', 'DOLLAR', 'TJ MAXX', 'MARSHALLS', 'ROSS',
                                       'BED BATH', 'IKEA', 'JEWI', 'JEWELRY']
        if any(kw in description for kw in general_merchandise_keywords):
            return 'General Merchandise'

        # Default to Other Expenses for unrecognized merchants
        return 'Other Expenses'

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
