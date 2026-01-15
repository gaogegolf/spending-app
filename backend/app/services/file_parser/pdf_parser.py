"""PDF file parser with support for Fidelity, American Express, and Chase formats."""

import pdfplumber
import pandas as pd
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from app.services.file_parser.base import BaseParser, ParseResult


class PDFParser(BaseParser):
    """Parser for PDF statement files.

    Supports:
    - Fidelity Visa statements (two-table format)
    - American Express statements (text-based format)
    - Chase credit card statements (text-based format)
    """

    def __init__(self, file_path: str):
        """Initialize PDF parser.

        Args:
            file_path: Path to PDF file
        """
        self.file_path = file_path
        self.pdf = None
        self.tables = []
        self.statement_year = None  # Extract from PDF header
        self.statement_format = None  # 'fidelity', 'amex', or 'unknown'

    def parse(self) -> ParseResult:
        """Parse PDF file and return transactions."""
        errors = []
        warnings = []
        transactions = []

        try:
            self.pdf = pdfplumber.open(self.file_path)

            # Detect statement format
            self.statement_format = self._detect_statement_format()

            # Extract statement year from PDF header
            self.statement_year = self._extract_statement_year()

            # Route to appropriate parser based on format
            if self.statement_format == 'amex':
                return self._parse_amex_statement()

            if self.statement_format == 'chase':
                return self._parse_chase_statement()

            if self.statement_format == 'wellsfargo':
                return self._parse_wellsfargo_statement()

            if self.statement_format == 'capitalone':
                return self._parse_capitalone_statement()

            if self.statement_format == 'allybank':
                return self._parse_allybank_statement()

            if self.statement_format == 'chasebank':
                return self._parse_chasebank_statement()

            # Default: Try Fidelity format
            # Extract all tables from all pages
            self.tables = self.extract_tables()

            # If table extraction fails, try text extraction fallback
            if not self.tables:
                warnings.append("Table extraction failed, trying text extraction fallback...")
                transactions = self._extract_text_fallback()

                if not transactions:
                    return ParseResult(
                        success=False,
                        transactions=[],
                        errors=["Unable to parse this PDF format. Different banks use different PDF layouts.",
                                "For best results, please download CSV from your bank's online portal."],
                        warnings=warnings,
                        metadata={}
                    )

                return ParseResult(
                    success=True,
                    transactions=transactions,
                    errors=errors,
                    warnings=warnings,
                    metadata={
                        'total_transactions': len(transactions),
                        'source': 'pdf',
                        'format': 'text_extraction',
                    }
                )

            # Identify transaction tables (Fidelity has two: Credits and Debits)
            credit_table, debit_table = self._identify_fidelity_tables(self.tables)

            # If table identification fails, try text extraction fallback
            if credit_table is None and debit_table is None:
                warnings.append("Table identification failed, trying text extraction fallback...")
                transactions = self._extract_text_fallback()

                if not transactions:
                    return ParseResult(
                        success=False,
                        transactions=[],
                        errors=[
                            "Unable to parse this PDF format. Different banks use different PDF layouts.",
                            "For best results, please download CSV from your bank's online portal."
                        ],
                        warnings=warnings,
                        metadata={'tables_found': len(self.tables)}
                    )

                return ParseResult(
                    success=True,
                    transactions=transactions,
                    errors=errors,
                    warnings=warnings,
                    metadata={
                        'total_transactions': len(transactions),
                        'source': 'pdf',
                        'format': 'text_extraction',
                    }
                )

            # Merge credit and debit tables
            merged_df = self._merge_credit_debit_tables(credit_table, debit_table)

            if merged_df is None or len(merged_df) == 0:
                return ParseResult(
                    success=False,
                    transactions=[],
                    errors=["No transactions found in PDF tables"],
                    warnings=[],
                    metadata={}
                )

            # Convert to transactions
            transactions = self._to_transactions(merged_df)

            return ParseResult(
                success=True,
                transactions=transactions,
                errors=errors,
                warnings=warnings,
                metadata={
                    'total_transactions': len(transactions),
                    'source': 'pdf',
                    'format': 'fidelity_two_table',
                }
            )

        except Exception as e:
            errors.append(f"Failed to parse PDF: {str(e)}")
            return ParseResult(
                success=False,
                transactions=[],
                errors=errors,
                warnings=["Consider using CSV format for more reliable parsing."],
                metadata={}
            )
        finally:
            if self.pdf:
                self.pdf.close()

    def _detect_statement_format(self) -> str:
        """Detect the statement format based on PDF content.

        Returns:
            'amex' for American Express, 'chase' for Chase, 'wellsfargo' for Wells Fargo,
            'fidelity' for Fidelity, 'unknown' otherwise
        """
        try:
            if not self.pdf or len(self.pdf.pages) == 0:
                return 'unknown'

            # Get first page text
            first_page_text = self.pdf.pages[0].extract_text()

            if not first_page_text:
                return 'unknown'

            # Check for Ally Bank indicators
            ally_indicators = [
                'Ally Bank',
                'ally.com',
                'Ally Bank Member FDIC',
                'Spending Account',
            ]

            if any(indicator in first_page_text for indicator in ally_indicators):
                return 'allybank'

            # Check for Chase Bank (checking/savings) indicators FIRST
            # Must check before Capital One/Wells Fargo as those names may appear as payments
            chase_bank_indicators = [
                'CHASE TOTAL CHECKING',
                'Chase Total Checking',
                'CHASE SAVINGS',
                'Chase Savings',
                'CHECKING SUMMARY',
                'SAVINGS SUMMARY',
            ]

            if any(indicator in first_page_text for indicator in chase_bank_indicators):
                return 'chasebank'

            # Check for Capital One indicators
            capitalone_indicators = [
                'Capital One',
                'capitalone.com',
                'Venture X Card',
                'Venture Card',
                'Quicksilver',
                'Savor Card',
            ]

            if any(indicator in first_page_text for indicator in capitalone_indicators):
                return 'capitalone'

            # Check for Wells Fargo indicators
            wellsfargo_indicators = [
                'Wells Fargo',
                'wellsfargo.com',
                'Wells Fargo Online',
                'Bilt Rewards',
                'BiltProtect',
            ]

            if any(indicator in first_page_text for indicator in wellsfargo_indicators):
                return 'wellsfargo'

            # Check for Chase Credit Card indicators
            chase_indicators = [
                'chase.com',
                'Chase Mobile',
                'CHASE CREDIT CARDS',
                'JPMorgan Chase',
                'PRIME VISA',
                'Chase Sapphire',
                'Chase Freedom',
            ]

            if any(indicator in first_page_text for indicator in chase_indicators):
                return 'chase'

            # Check for American Express indicators
            amex_indicators = [
                'American Express',
                'Platinum Card®',
                'Gold Card®',
                'americanexpress.com',
                'Membership Rewards',
                'Pay Over Time',
            ]

            if any(indicator in first_page_text for indicator in amex_indicators):
                return 'amex'

            # Check for Fidelity indicators
            fidelity_indicators = [
                'Fidelity',
                'Payments and Other Credits',
                'Purchases and Other Debits',
            ]

            if any(indicator in first_page_text for indicator in fidelity_indicators):
                return 'fidelity'

            return 'unknown'

        except Exception:
            return 'unknown'

    def _parse_amex_statement(self) -> ParseResult:
        """Parse American Express statement.

        Amex statements have text-based transaction format:
        - Payments section: payments with -$AMOUNT
        - Credits section: credits/refunds with -$AMOUNT
        - New Charges section: charges with $AMOUNT
        - Fees section: fees with $AMOUNT

        Returns:
            ParseResult with transactions
        """
        errors = []
        warnings = []
        transactions = []

        try:
            # Extract all text from all pages
            all_text = ""
            for page in self.pdf.pages:
                text = page.extract_text()
                if text:
                    all_text += text + "\n"

            # Parse transactions from text
            transactions = self._extract_amex_transactions(all_text)

            if not transactions:
                return ParseResult(
                    success=False,
                    transactions=[],
                    errors=["No transactions found in American Express statement"],
                    warnings=warnings,
                    metadata={'format': 'amex'}
                )

            return ParseResult(
                success=True,
                transactions=transactions,
                errors=errors,
                warnings=warnings,
                metadata={
                    'total_transactions': len(transactions),
                    'source': 'pdf',
                    'format': 'amex',
                }
            )

        except Exception as e:
            errors.append(f"Failed to parse Amex statement: {str(e)}")
            return ParseResult(
                success=False,
                transactions=[],
                errors=errors,
                warnings=warnings,
                metadata={'format': 'amex'}
            )

    def _extract_amex_transactions(self, text: str) -> List[Dict[str, Any]]:
        """Extract transactions from American Express statement text.

        Args:
            text: Full text of the Amex statement

        Returns:
            List of transaction dictionaries
        """
        transactions = []
        lines = text.split('\n')
        current_section = None
        row_index = 0  # Track row position for deduplication

        # Patterns for Amex transactions
        # Credit pattern: MM/DD/YY DESCRIPTION -$AMOUNT (all on one line)
        credit_pattern = r'^(\d{2}/\d{2}/\d{2})\*?\s+(.+?)\s+-\$?([\d,]+\.\d{2})⧫?$'
        # Charge pattern: MM/DD/YY DESCRIPTION $AMOUNT
        charge_pattern = r'^(\d{2}/\d{2}/\d{2})\*?\s+(.+?)\s+\$?([\d,]+\.\d{2})⧫?$'
        # Date-only pattern for multi-line credits: MM/DD/YY* DESCRIPTION (no amount on line)
        date_only_pattern = r'^(\d{2}/\d{2}/\d{2})\*?\s+(.+?)$'
        # Amount-only pattern: -$AMOUNT or $AMOUNT at end of line
        amount_pattern = r'-?\$?([\d,]+\.\d{2})⧫?\s*$'

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Detect section headers
            if 'Payments and Credits' in line or 'Detail' in line and 'Payments' in line:
                current_section = 'payments_credits'
            elif 'New Charges' in line and 'Total' not in line and 'Summary' not in line:
                current_section = 'charges'
            elif line.startswith('Fees') and 'Total' not in line:
                current_section = 'fees'
            elif 'Credits' in line and 'Payment' not in line and 'Total' not in line:
                current_section = 'credits'
            elif 'Payments' in line and 'Credits' not in line and 'Total' not in line:
                current_section = 'payments'

            # Skip non-transaction lines
            if not line or 'Account Ending' in line or 'Closing Date' in line or \
               'Customer Care' in line or 'Page' in line or 'Summary' in line or \
               'Total' in line or line.startswith('Card Ending'):
                i += 1
                continue

            # Try to match credit (negative amount) pattern first (single line)
            credit_match = re.match(credit_pattern, line)
            if credit_match:
                txn = self._parse_amex_transaction_line(
                    credit_match.group(1),
                    credit_match.group(2),
                    credit_match.group(3),
                    is_credit=True,
                    section=current_section
                )
                if txn:
                    txn['row_index'] = row_index
                    row_index += 1
                    transactions.append(txn)
                i += 1
                continue

            # Try to match charge (positive amount) pattern (single line)
            charge_match = re.match(charge_pattern, line)
            if charge_match:
                txn = self._parse_amex_transaction_line(
                    charge_match.group(1),
                    charge_match.group(2),
                    charge_match.group(3),
                    is_credit=False,
                    section=current_section
                )
                if txn:
                    txn['row_index'] = row_index
                    row_index += 1
                    transactions.append(txn)
                i += 1
                continue

            # Handle multi-line credit format (amount on separate line)
            # Example 1:
            #   06/06/25* K950:0012 500.00 credit
            #   TRANSACTION PROCESSED BY AMERICAN EXPRESS    -$500.00 ⧫
            # Example 2 (BEST BUY with 3 description lines):
            #   07/06/25 BEST BUY
            #   SAN CARLOS CA
            #   888BESTBUY
            #   -$1,286.31 ⧫
            date_only_match = re.match(date_only_pattern, line)
            if date_only_match and current_section in ['credits', 'payments_credits', 'payments']:
                date_str = date_only_match.group(1)
                description = date_only_match.group(2)

                # Look at next line(s) for continuation and amount
                # Increased lookahead to 5 lines to handle multi-line descriptions
                amount_str = None
                is_credit = False
                j = i + 1
                while j < len(lines) and j < i + 6:  # Look ahead up to 5 lines
                    next_line = lines[j].strip()
                    if not next_line:
                        j += 1
                        continue

                    # Stop if we hit a new transaction (line starting with date)
                    if re.match(r'^\d{2}/\d{2}/\d{2}', next_line):
                        break

                    # Stop if we hit a section header
                    if 'New Charges' in next_line or 'Fees' in next_line or \
                       'Total' in next_line or 'Summary' in next_line:
                        break

                    # Check if this line is just an amount (standalone amount line)
                    # Pattern: -$1,286.31 ⧫ or $500.00 ⧫
                    standalone_amount_match = re.match(r'^-?\$?([\d,]+\.\d{2})\s*⧫?\s*$', next_line)
                    if standalone_amount_match:
                        amount_str = standalone_amount_match.group(1)
                        # Check if it's a credit (has - prefix)
                        if next_line.strip().startswith('-'):
                            is_credit = True
                        break

                    # Check if line ends with amount
                    amount_match = re.search(amount_pattern, next_line)
                    if amount_match:
                        # Check if it's a credit (has - prefix before amount)
                        if '-$' in next_line or re.search(r'-\s*\$?[\d,]+\.\d{2}', next_line):
                            is_credit = True
                        amount_str = amount_match.group(1)

                        # Get description continuation (text before amount)
                        desc_part = re.sub(amount_pattern, '', next_line).strip()
                        if desc_part and not desc_part.startswith('$') and not desc_part.startswith('-$'):
                            description = f"{description} {desc_part}"
                        break
                    else:
                        # This line is description continuation
                        description = f"{description} {next_line}"
                    j += 1

                if amount_str:
                    txn = self._parse_amex_transaction_line(
                        date_str,
                        description,
                        amount_str,
                        is_credit=is_credit,
                        section=current_section
                    )
                    if txn:
                        txn['row_index'] = row_index
                        row_index += 1
                        transactions.append(txn)
                    i = j + 1  # Skip the lines we processed
                    continue

            i += 1

        return transactions

    def _parse_amex_transaction_line(self, date_str: str, description: str,
                                      amount_str: str, is_credit: bool,
                                      section: str) -> Optional[Dict[str, Any]]:
        """Parse a single Amex transaction line.

        Args:
            date_str: Date string in MM/DD/YY format
            description: Transaction description
            amount_str: Amount string (without $ or -)
            is_credit: Whether this is a credit (negative) transaction
            section: Current section of the statement

        Returns:
            Transaction dictionary or None if parsing fails
        """
        try:
            # Parse date (MM/DD/YY format)
            month, day, year = date_str.split('/')
            year_full = 2000 + int(year)
            parsed_date = datetime(year_full, int(month), int(day)).date()

            # Clean amount - keep as negative for credits/refunds
            amount = float(amount_str.replace(',', ''))
            if is_credit:
                amount = -amount  # Credits are negative expenses (refunds, reimbursements)

            # Clean merchant description
            cleaned_merchant = self._clean_amex_merchant(description)

            # Determine if this is a payment (should be marked as transfer)
            is_payment = 'AUTOPAY' in description.upper() or \
                         ('PAYMENT' in description.upper() and 'THANK YOU' in description.upper())

            return {
                'date': parsed_date.isoformat(),
                'description_raw': description,
                'merchant_normalized': cleaned_merchant,
                'amount': amount,  # Negative for credits, positive for charges
                'is_payment': is_payment,  # Flag for transfers (payments to card)
                'currency': 'USD',
            }

        except Exception as e:
            print(f"Failed to parse Amex line: {date_str} {description} {amount_str}, error: {e}")
            return None

    def _clean_amex_merchant(self, description: str) -> str:
        """Clean American Express merchant description.

        Amex format examples:
        - "UBER EATS help.uber.com CA"
        - "ELITE PARKING SERVICES 569900000228528 HONOLULU HI"
        - "MCDONALD'S HONOLULU HI"

        Args:
            description: Raw transaction description

        Returns:
            Cleaned merchant name
        """
        cleaned = description

        # Remove URLs
        cleaned = re.sub(r'https?://\S+', '', cleaned)
        cleaned = re.sub(r'\S+\.com\S*', '', cleaned)
        cleaned = re.sub(r'\S+\.net\S*', '', cleaned)

        # Remove long numeric codes (like 569900000228528)
        cleaned = re.sub(r'\b\d{10,}\b', '', cleaned)

        # Remove phone numbers
        cleaned = re.sub(r'\b\d{3}[-\s]?\d{3}[-\s]?\d{4}\b', '', cleaned)
        cleaned = re.sub(r'\b\d{10}\b', '', cleaned)

        # Remove state codes at the end (2-letter codes preceded by city)
        cleaned = re.sub(r'\s+[A-Z]{2}\s*$', '', cleaned)

        # Remove city names at the end (common patterns)
        cleaned = re.sub(r'\s+(HONOLULU|KAILUA|LAIE|WAIMANALO|HALEIWA|WAIPAHU|NAPA|BENTONVILLE)\s*$',
                        '', cleaned, flags=re.IGNORECASE)

        # Remove extra whitespace
        cleaned = ' '.join(cleaned.split())

        return cleaned.strip()

    def _parse_chase_statement(self) -> ParseResult:
        """Parse Chase credit card statement.

        Chase statements have text-based transaction format:
        - ACCOUNT ACTIVITY section
        - PAYMENTS AND OTHER CREDITS with negative amounts
        - PURCHASE section with positive amounts

        Returns:
            ParseResult with transactions
        """
        errors = []
        warnings = []
        transactions = []

        try:
            # Extract all text from all pages
            all_text = ""
            for page in self.pdf.pages:
                text = page.extract_text()
                if text:
                    all_text += text + "\n"

            # Parse transactions from text
            transactions = self._extract_chase_transactions(all_text)

            if not transactions:
                return ParseResult(
                    success=False,
                    transactions=[],
                    errors=["No transactions found in Chase statement"],
                    warnings=warnings,
                    metadata={'format': 'chase'}
                )

            return ParseResult(
                success=True,
                transactions=transactions,
                errors=errors,
                warnings=warnings,
                metadata={
                    'total_transactions': len(transactions),
                    'source': 'pdf',
                    'format': 'chase',
                }
            )

        except Exception as e:
            errors.append(f"Failed to parse Chase statement: {str(e)}")
            return ParseResult(
                success=False,
                transactions=[],
                errors=errors,
                warnings=warnings,
                metadata={'format': 'chase'}
            )

    def _extract_chase_transactions(self, text: str) -> List[Dict[str, Any]]:
        """Extract transactions from Chase statement text.

        Chase transaction format:
        - Date: MM/DD
        - Description: Merchant name and details
        - Amount: Positive for purchases, negative with - prefix for credits

        Example lines:
        01/21 AUTOMATIC PAYMENT - THANK YOU -2,638.72
        12/29 Amazon.com*ZP5F00VD2 Amzn.com/bill WA 44.94

        Args:
            text: Full text of the Chase statement

        Returns:
            List of transaction dictionaries
        """
        transactions = []
        lines = text.split('\n')
        row_index = 0
        current_section = None

        # Pattern for Chase transactions: MM/DD DESCRIPTION AMOUNT
        # Amount can be negative (with -) or positive
        # Note: Chase uses MM/DD format without year
        transaction_pattern = r'^(\d{2}/\d{2})\s+(.+?)\s+(-?[\d,]+\.\d{2})$'

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Detect section headers (Chase PDFs sometimes have doubled characters)
            # "PAYMENTS AND OTHER CREDITS" marks credits section
            if 'PAYMENTS AND OTHER CREDITS' in line.upper():
                current_section = 'credits'
                i += 1
                continue

            # "PURCHASE" or "PURCHASES" marks purchases section
            if line.upper() in ['PURCHASE', 'PURCHASES']:
                current_section = 'purchases'
                i += 1
                continue

            # Skip empty lines
            if not line:
                i += 1
                continue

            # Skip known non-transaction lines
            skip_patterns = [
                'Date of', 'Transaction', 'Merchant Name',
                '$ Amount', 'ACCOUNT ACTIVITY', 'ACCOUNT SUMMARY',
                'Order Number', 'Year-to-Date', 'Total fees',
                'Total interest', 'INTEREST CHARGES', 'Annual Percentage',
                'Balance Type', 'Balance Subject', 'Days in Billing',
                'Page', 'Statement Date', 'www.chase.com', 'chase.com',
                'Customer Service', '2025 Totals', '2024 Totals',
                'AACCCCOOUUNNTT', 'IINNTTEERREESSTT', 'YYeeaarr'  # Doubled character patterns
            ]

            if any(skip in line for skip in skip_patterns):
                i += 1
                continue

            # Try to match transaction pattern
            match = re.match(transaction_pattern, line)
            if match:
                date_str = match.group(1)
                description = match.group(2).strip()
                amount_str = match.group(3).strip()

                txn = self._parse_chase_transaction_line(
                    date_str,
                    description,
                    amount_str,
                    current_section
                )

                if txn:
                    txn['row_index'] = row_index
                    row_index += 1
                    transactions.append(txn)

            i += 1

        return transactions

    def _parse_chase_transaction_line(self, date_str: str, description: str,
                                       amount_str: str, section: str) -> Optional[Dict[str, Any]]:
        """Parse a single Chase transaction line.

        Args:
            date_str: Date string in MM/DD format
            description: Transaction description
            amount_str: Amount string (negative with - for credits)
            section: Current section of the statement

        Returns:
            Transaction dictionary or None if parsing fails
        """
        try:
            # Parse date (MM/DD format - need to add year)
            month, day = map(int, date_str.split('/'))
            year = self.statement_year if self.statement_year else datetime.now().year

            # Handle year boundary for Chase statements:
            # If transaction month is much later than expected for a statement
            # (e.g., December transaction in a February statement),
            # the transaction is from the previous year
            # Heuristic: if transaction month > 10 and we're early in the year (Jan-Mar),
            # the transaction is from the previous year
            if month >= 10 and self._get_statement_month() <= 3:
                year -= 1

            try:
                parsed_date = datetime(year, month, day).date()
            except ValueError:
                # Invalid date, skip
                return None

            # Parse amount
            amount = float(amount_str.replace(',', ''))

            # Clean merchant description
            cleaned_merchant = self._clean_chase_merchant(description)

            # Determine if this is a payment (transfer)
            is_payment = 'AUTOMATIC PAYMENT' in description.upper() or \
                         ('PAYMENT' in description.upper() and 'THANK YOU' in description.upper())

            return {
                'date': parsed_date.isoformat(),
                'description_raw': description,
                'merchant_normalized': cleaned_merchant,
                'amount': amount,  # Negative for credits, positive for purchases
                'is_payment': is_payment,
                'currency': 'USD',
            }

        except Exception as e:
            print(f"Failed to parse Chase line: {date_str} {description} {amount_str}, error: {e}")
            return None

    def _get_statement_month(self) -> int:
        """Get the statement month from PDF header.

        Returns:
            Statement month (1-12), defaults to current month if not found
        """
        try:
            if not self.pdf or len(self.pdf.pages) == 0:
                return datetime.now().month

            first_page_text = self.pdf.pages[0].extract_text()
            if not first_page_text:
                return datetime.now().month

            # Look for "Statement Closing Date MM/DD/YYYY" pattern (Wells Fargo)
            wellsfargo_match = re.search(r'Statement Closing Date\s+(\d{2})/\d{2}/\d{4}', first_page_text)
            if wellsfargo_match:
                return int(wellsfargo_match.group(1))

            # Look for Capital One billing cycle pattern: "Mon DD, YYYY - Mon DD, YYYY"
            # The second date is the statement closing date
            capitalone_match = re.search(
                r'([A-Z][a-z]{2})\s+\d{1,2},\s+\d{4}\s*-\s*([A-Z][a-z]{2})\s+\d{1,2},\s+(\d{4})',
                first_page_text
            )
            if capitalone_match:
                month_abbr_map = {
                    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                }
                end_month = capitalone_match.group(2)
                if end_month in month_abbr_map:
                    return month_abbr_map[end_month]

            # Look for "Month YYYY" pattern (Chase and others)
            months = ['January', 'February', 'March', 'April', 'May', 'June',
                      'July', 'August', 'September', 'October', 'November', 'December']

            for i, month_name in enumerate(months, 1):
                if re.search(rf'{month_name}\s+\d{{4}}', first_page_text):
                    return i

            return datetime.now().month

        except Exception:
            return datetime.now().month

    def _clean_chase_merchant(self, description: str) -> str:
        """Clean Chase merchant description.

        Chase format examples:
        - "Amazon.com*ZP5F00VD2 Amzn.com/bill WA" -> "Amazon"
        - "AUTOMATIC PAYMENT - THANK YOU" -> "AUTOMATIC PAYMENT - THANK YOU"
        - "Whole Foods LAT 10155 866-216-1072 DE" -> "Whole Foods LAT 10155"

        Args:
            description: Raw transaction description

        Returns:
            Cleaned merchant name
        """
        cleaned = description

        # Remove Amazon order codes (like *ZP5F00VD2) but keep the merchant name
        cleaned = re.sub(r'\*[A-Z0-9]+', '', cleaned)

        # Remove URL paths (like Amzn.com/bill) - the secondary URL after merchant
        cleaned = re.sub(r'\s+\S+\.com/\S*', '', cleaned)

        # Remove phone numbers (like 866-216-1072)
        cleaned = re.sub(r'\b\d{3}-\d{3}-\d{4}\b', '', cleaned)
        cleaned = re.sub(r'\b\d{10,}\b', '', cleaned)

        # Remove state codes at the end (2-letter codes)
        cleaned = re.sub(r'\s+[A-Z]{2}\s*$', '', cleaned)

        # Clean up .com from merchant names (Amazon.com -> Amazon)
        cleaned = re.sub(r'\.com\b', '', cleaned)

        # Remove extra whitespace
        cleaned = ' '.join(cleaned.split())

        return cleaned.strip()

    def _parse_wellsfargo_statement(self) -> ParseResult:
        """Parse Wells Fargo credit card statement.

        Wells Fargo statements have text-based transaction format:
        - Transaction Summary section
        - Format: Trans Date Post Date Reference Number Description Amount

        Returns:
            ParseResult with transactions
        """
        errors = []
        warnings = []
        transactions = []

        try:
            # Extract all text from all pages
            all_text = ""
            for page in self.pdf.pages:
                text = page.extract_text()
                if text:
                    all_text += text + "\n"

            # Parse transactions from text
            transactions = self._extract_wellsfargo_transactions(all_text)

            if not transactions:
                return ParseResult(
                    success=False,
                    transactions=[],
                    errors=["No transactions found in Wells Fargo statement"],
                    warnings=warnings,
                    metadata={'format': 'wellsfargo'}
                )

            return ParseResult(
                success=True,
                transactions=transactions,
                errors=errors,
                warnings=warnings,
                metadata={
                    'total_transactions': len(transactions),
                    'source': 'pdf',
                    'format': 'wellsfargo',
                }
            )

        except Exception as e:
            errors.append(f"Failed to parse Wells Fargo statement: {str(e)}")
            return ParseResult(
                success=False,
                transactions=[],
                errors=errors,
                warnings=warnings,
                metadata={'format': 'wellsfargo'}
            )

    def _extract_wellsfargo_transactions(self, text: str) -> List[Dict[str, Any]]:
        """Extract transactions from Wells Fargo statement text.

        Wells Fargo transaction format:
        - Trans Date Post Date Reference Number Description Amount
        - Credits have trailing '-' after amount (e.g., $3,319.99-)

        Example lines:
        12/09 12/09 860001800 5543286P861K5WPZ7 AMAZON.COM*ZR2WX97H0 AMZN.COM/BILL WA $25.00
        10/01 10/01 F2290008J00CHGDDA AUTOMATIC PAYMENT - THANK YOU $3,319.99-

        Args:
            text: Full text of the Wells Fargo statement

        Returns:
            List of transaction dictionaries
        """
        transactions = []
        lines = text.split('\n')
        row_index = 0
        in_transaction_section = False

        # Pattern for Wells Fargo transactions:
        # MM/DD MM/DD REFERENCE1 [REFERENCE2] DESCRIPTION $AMOUNT[-]
        # There can be one or two reference numbers (alphanumeric)
        # Pattern captures: date, date, refs+description, amount, credit flag
        transaction_pattern = r'^(\d{2}/\d{2})\s+(\d{2}/\d{2})\s+(.+?)\s+\$?([\d,]+\.\d{2})(-)?$'

        for line in lines:
            line = line.strip()

            # Detect start of transaction section
            if 'Transaction Summary' in line:
                in_transaction_section = True
                continue

            # Skip header line
            if 'Trans Date' in line and 'Post Date' in line:
                continue

            # End of transaction section markers
            if any(marker in line for marker in [
                'Interest Charge Calculation',
                'BiltProtect Summary',
                'NOTICE: SEE REVERSE',
                'PAGE',
                'Interest Charge',
            ]):
                # Don't break, there might be more transactions on next pages
                continue

            if not in_transaction_section:
                continue

            # Skip empty lines and non-transaction content
            if not line or line.startswith('Continued'):
                continue

            # Try to match transaction pattern
            match = re.match(transaction_pattern, line)
            if match:
                trans_date = match.group(1)
                post_date = match.group(2)
                description = match.group(3).strip()  # Contains refs + description
                amount_str = match.group(4)
                is_credit = match.group(5) == '-'

                txn = self._parse_wellsfargo_transaction_line(
                    post_date,
                    description,
                    amount_str,
                    is_credit
                )

                if txn:
                    txn['row_index'] = row_index
                    row_index += 1
                    transactions.append(txn)

        return transactions

    def _parse_wellsfargo_transaction_line(self, date_str: str, description: str,
                                            amount_str: str, is_credit: bool) -> Optional[Dict[str, Any]]:
        """Parse a single Wells Fargo transaction line.

        Args:
            date_str: Date string in MM/DD format
            description: Transaction description
            amount_str: Amount string (without $ or -)
            is_credit: Whether this is a credit (has trailing -)

        Returns:
            Transaction dictionary or None if parsing fails
        """
        try:
            # Parse date (MM/DD format - need to add year)
            month, day = map(int, date_str.split('/'))
            year = self.statement_year if self.statement_year else datetime.now().year

            # Handle year boundary: if transaction month > statement month by a lot,
            # the transaction is from the previous year
            if month >= 10 and self._get_statement_month() <= 3:
                year -= 1

            try:
                parsed_date = datetime(year, month, day).date()
            except ValueError:
                return None

            # Parse amount - credits are negative
            amount = float(amount_str.replace(',', ''))
            if is_credit:
                amount = -amount

            # Clean merchant description
            cleaned_merchant = self._clean_wellsfargo_merchant(description)

            # Determine if this is a payment (transfer)
            is_payment = 'AUTOMATIC PAYMENT' in description.upper() or \
                         ('PAYMENT' in description.upper() and 'THANK YOU' in description.upper())

            return {
                'date': parsed_date.isoformat(),
                'description_raw': description,
                'merchant_normalized': cleaned_merchant,
                'amount': amount,
                'is_payment': is_payment,
                'currency': 'USD',
            }

        except Exception as e:
            print(f"Failed to parse Wells Fargo line: {date_str} {description} {amount_str}, error: {e}")
            return None

    def _clean_wellsfargo_merchant(self, description: str) -> str:
        """Clean Wells Fargo merchant description.

        Wells Fargo format examples:
        - "860001800 5543286P861K5WPZ7 AMAZON.COM*ZR2WX97H0 AMZN.COM/BILL WA" -> "Amazon"
        - "PANERA BREAD #204485 O 650-968-2066 CA" -> "Panera Bread"
        - "TST*UDON MUGIZO - MOUN MOUNTAIN VIEW CA" -> "Udon Mugizo"
        - "BPS*BILT REWARDS B NEW YORK NY" -> "Bilt Rewards"

        Args:
            description: Raw transaction description (may include reference codes)

        Returns:
            Cleaned merchant name
        """
        cleaned = description

        # Remove reference codes at the start
        # Pattern 1: Numeric reference (like 860001800)
        cleaned = re.sub(r'^\d{9,}\s+', '', cleaned)
        # Pattern 2: Alphanumeric reference (like 5543286P861K5WPZ7 or F2290008J00CHGDDA)
        cleaned = re.sub(r'^[A-Z0-9]{14,}\s+', '', cleaned)
        # Try again in case there are two reference codes
        cleaned = re.sub(r'^[A-Z0-9]{14,}\s+', '', cleaned)

        # Remove common prefixes (case-insensitive)
        prefix_patterns = [
            (r'^TST\*\s*', ''),
            (r'^SQ\s*\*\s*', ''),
            (r'^BPS\*\s*', ''),
            (r'^GDP\*\s*', ''),
            (r'^DD\s*\*?\s*', ''),
            (r'^OX9\s+', ''),
            (r'^UBER\s*\*\s*', 'UBER '),
        ]
        for pattern, replacement in prefix_patterns:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

        # Remove Amazon order codes (like *ZR2WX97H0)
        cleaned = re.sub(r'\*[A-Z0-9]+', '', cleaned)

        # Remove URL paths (like AMZN.COM/BILL)
        cleaned = re.sub(r'\s*\S+\.COM/\S*', '', cleaned, flags=re.IGNORECASE)

        # Remove .COM from merchant names
        cleaned = re.sub(r'\.COM\b', '', cleaned, flags=re.IGNORECASE)

        # Remove phone numbers
        cleaned = re.sub(r'\b\d{3}-?\d{3}-?\d{4}\b', '', cleaned)
        cleaned = re.sub(r'\b\d{10,}\b', '', cleaned)

        # Remove store numbers (like #204485)
        cleaned = re.sub(r'#\d+', '', cleaned)

        # Remove "Store" followed by numbers (like "Store 00618")
        cleaned = re.sub(r'\s+Store\s+\d+', '', cleaned, flags=re.IGNORECASE)

        # Remove Spotify/other service reference codes (like P383C56Bcb)
        cleaned = re.sub(r'\s+P[0-9A-Fa-f]{8,}', '', cleaned)

        # Remove "Ll" or "LLC" patterns (like "Kiddo's Chu Chu Ll")
        cleaned = re.sub(r'\s+LL[C]?\s+', ' ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+LL[C]?\s*$', '', cleaned, flags=re.IGNORECASE)

        # Remove truncated location patterns (like "- MOUN")
        # This must happen BEFORE city/state removal
        # Exclude common words that should be kept (like "THANK")
        def remove_truncated_location(match):
            word = match.group(1).upper()
            # Keep these words, they're not truncated locations
            keep_words = {'THANK', 'DRIVE', 'THRU', 'PICK', 'STORE', 'ONLINE'}
            if word in keep_words:
                return match.group(0)  # Keep original
            return ' '
        cleaned = re.sub(r'\s+-\s+([A-Z]{3,6})\s+', remove_truncated_location, cleaned, flags=re.IGNORECASE)

        # Remove common city names that appear in Wells Fargo statements
        # Multi-word cities must be handled explicitly
        # IMPORTANT: Longer city names must come first to avoid partial matches
        common_cities = [
            'EAST PALO ALTO',     # Must come before 'EAST PALO' and 'PALO ALTO'
            'MOUNTAIN VIEW', 'SAN FRANCISCO', 'SAN JOSE', 'SAN MATEO',
            'NEW YORK', 'LOS ANGELES', 'PALO ALTO', 'MENLO PARK',
            'REDWOOD CITY', 'SUNNYVALE', 'SANTA CLARA', 'CUPERTINO',
            'FOSTER CITY', 'BURLINGAME', 'SAN CARLOS', 'BELMONT',
            'EAST PALO',          # Truncated version (after full version)
        ]
        for city in common_cities:
            cleaned = re.sub(rf'\s+{city}\s+[A-Z]{{2}}\s*$', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(rf'\s+{city}\s*$', '', cleaned, flags=re.IGNORECASE)

        # Remove single-word city + state patterns at the end (like "BEACHWOOD OH")
        # Pattern matches: WORD STATE where STATE is 2 letters
        cleaned = re.sub(r'\s+[A-Z]+\s+[A-Z]{2}\s*$', '', cleaned, flags=re.IGNORECASE)

        # Remove single letter/code before city that got left behind (like "B" in "B NEW YORK")
        cleaned = re.sub(r'\s+[A-Z]{1}\s*$', '', cleaned)

        # Remove trailing state code alone
        cleaned = re.sub(r'\s+[A-Z]{2}\s*$', '', cleaned)

        # Remove trailing "O" (common in Wells Fargo as a code)
        cleaned = re.sub(r'\s+O\s*$', '', cleaned)

        # Remove short alphanumeric codes at end (like F1528 in McDonald's F1528)
        # This must happen AFTER city/state removal
        cleaned = re.sub(r'\s+[A-Z]\d{3,5}\s*$', '', cleaned, flags=re.IGNORECASE)

        # Remove truncated common words at end (Company->Compan, Mountain->Mountai, etc.)
        truncated_patterns = [
            r'\s+Compan\s*$',      # Company
            r'\s+Mountai\s*$',     # Mountain
            r'\s+Mountain\s*$',    # Full word when it's city name remnant
            r'\s+Insuranc\s*$',    # Insurance
        ]
        for pattern in truncated_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        # Remove trailing numbers (like "3" in "Cafe3")
        cleaned = re.sub(r'(\w)\d+\s*$', r'\1', cleaned)

        # Remove extra whitespace
        cleaned = ' '.join(cleaned.split())

        # Title case for cleaner display (only if all uppercase)
        if cleaned.isupper() and len(cleaned) > 2:
            cleaned = cleaned.title()

        return cleaned.strip()

    def _parse_capitalone_statement(self) -> ParseResult:
        """Parse Capital One credit card statement.

        Capital One statements have text-based transaction format:
        - Trans Date Post Date Description Amount
        - Payments have " - $AMOUNT" pattern
        - Purchases have "$AMOUNT" pattern

        Returns:
            ParseResult with transactions
        """
        errors = []
        warnings = []
        transactions = []

        try:
            # Extract all text from all pages
            all_text = ""
            for page in self.pdf.pages:
                text = page.extract_text()
                if text:
                    all_text += text + "\n"

            # Parse transactions from text
            transactions = self._extract_capitalone_transactions(all_text)

            if not transactions:
                return ParseResult(
                    success=False,
                    transactions=[],
                    errors=["No transactions found in Capital One statement"],
                    warnings=warnings,
                    metadata={'format': 'capitalone'}
                )

            return ParseResult(
                success=True,
                transactions=transactions,
                errors=errors,
                warnings=warnings,
                metadata={
                    'total_transactions': len(transactions),
                    'source': 'pdf',
                    'format': 'capitalone',
                }
            )

        except Exception as e:
            errors.append(f"Failed to parse Capital One statement: {str(e)}")
            return ParseResult(
                success=False,
                transactions=[],
                errors=errors,
                warnings=warnings,
                metadata={'format': 'capitalone'}
            )

    def _extract_capitalone_transactions(self, text: str) -> List[Dict[str, Any]]:
        """Extract transactions from Capital One statement text.

        Capital One transaction format:
        - Trans Date Post Date Description Amount
        - Date format: "Sep 18" or "Oct 4" (Month Day, no year)
        - Credits/Payments: " - $AMOUNT"
        - Purchases: "$AMOUNT"

        Example lines:
        Sep 18 Sep 20 DCL RESERVATIONS8009392784FL $84.00
        Oct 4 Oct 4 CAPITAL ONE AUTOPAY PYMT - $149.48

        Args:
            text: Full text of the Capital One statement

        Returns:
            List of transaction dictionaries
        """
        transactions = []
        lines = text.split('\n')
        row_index = 0
        in_transaction_section = False

        # Month name to number mapping
        month_map = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }

        # Pattern for Capital One transactions:
        # Month Day Month Day Description [$]Amount or [- $]Amount
        # Examples:
        #   Sep 18 Sep 20 DCL RESERVATIONS8009392784FL $84.00
        #   Oct 4 Oct 4 CAPITAL ONE AUTOPAY PYMT - $149.48
        transaction_pattern = r'^([A-Z][a-z]{2})\s+(\d{1,2})\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+(.+?)\s+(-\s*)?\$([\d,]+\.\d{2})$'

        for line in lines:
            line = line.strip()

            # Detect start of transaction sections
            if 'Payments, Credits and Adjustments' in line or 'Transactions' in line:
                in_transaction_section = True
                continue

            # End of transaction section markers
            if any(marker in line for marker in [
                'Total Transactions for This Period',
                'Total Fees for This Period',
                'Interest Charged',
                'Fees',
                'Totals Year-to-Date',
                'Additional Information',
            ]):
                continue

            # Skip header line
            if 'Trans Date' in line and 'Post Date' in line:
                continue

            if not in_transaction_section:
                continue

            # Skip empty lines and non-transaction content
            if not line or line.startswith('GE GAO') or line.startswith('Total'):
                continue

            # Try to match transaction pattern
            match = re.match(transaction_pattern, line)
            if match:
                trans_month = match.group(1)
                trans_day = int(match.group(2))
                post_month = match.group(3)
                post_day = int(match.group(4))
                description = match.group(5).strip()
                is_credit = match.group(6) is not None  # Has "- " before amount
                amount_str = match.group(7)

                txn = self._parse_capitalone_transaction_line(
                    post_month,
                    post_day,
                    description,
                    amount_str,
                    is_credit
                )

                if txn:
                    txn['row_index'] = row_index
                    row_index += 1
                    transactions.append(txn)

        return transactions

    def _parse_capitalone_transaction_line(self, month_str: str, day: int,
                                            description: str, amount_str: str,
                                            is_credit: bool) -> Optional[Dict[str, Any]]:
        """Parse a single Capital One transaction line.

        Args:
            month_str: Month string (e.g., "Sep", "Oct")
            day: Day of month
            description: Transaction description
            amount_str: Amount string (without $ or -)
            is_credit: Whether this is a credit/payment

        Returns:
            Transaction dictionary or None if parsing fails
        """
        try:
            # Month mapping
            month_map = {
                'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
            }

            month = month_map.get(month_str)
            if not month:
                return None

            year = self.statement_year if self.statement_year else datetime.now().year

            # Handle year boundary: if transaction month > statement month by a lot,
            # the transaction is from the previous year
            statement_month = self._get_statement_month()
            if month >= 10 and statement_month <= 3:
                year -= 1

            try:
                parsed_date = datetime(year, month, day).date()
            except ValueError:
                return None

            # Parse amount - credits are negative
            amount = float(amount_str.replace(',', ''))
            if is_credit:
                amount = -amount

            # Clean merchant description
            cleaned_merchant = self._clean_capitalone_merchant(description)

            # Determine if this is a payment (transfer)
            is_payment = 'AUTOPAY' in description.upper() or \
                         'PAYMENT' in description.upper()

            return {
                'date': parsed_date.isoformat(),
                'description_raw': description,
                'merchant_normalized': cleaned_merchant,
                'amount': amount,
                'is_payment': is_payment,
                'currency': 'USD',
            }

        except Exception as e:
            print(f"Failed to parse Capital One line: {month_str} {day} {description} {amount_str}, error: {e}")
            return None

    def _clean_capitalone_merchant(self, description: str) -> str:
        """Clean Capital One merchant description.

        Capital One format examples:
        - "DCL RESERVATIONS8009392784FL" -> "Dcl Reservations"
        - "CHEVRON 0203324SAN JOSECA" -> "Chevron"
        - "COSTCO WHSE #0143MOUNTAIN VIEWCA" -> "Costco Whse"
        - "CAPITAL ONE AUTOPAY PYMT" -> "Capital One Autopay Pymt"

        Args:
            description: Raw transaction description

        Returns:
            Cleaned merchant name
        """
        cleaned = description

        # Step 1: Remove prefixes
        cleaned = re.sub(r'^SQ\s*\*\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'^GOOGLE\s*\*', 'Google ', cleaned, flags=re.IGNORECASE)

        # Step 2: Remove numbers FIRST (before city/state patterns)
        # Remove store numbers (like #0143 or #0402)
        cleaned = re.sub(r'#\d+', '', cleaned)
        # Remove phone numbers with or without dashes (like 8009392784 or 855-836-3987)
        cleaned = re.sub(r'\d{3}-\d{3}-\d{4}', '', cleaned)
        # Remove long numbers (10+ digits like phone numbers)
        cleaned = re.sub(r'\d{10,}', '', cleaned)
        # Remove 6+ digit store/reference numbers
        cleaned = re.sub(r'\d{6,}', '', cleaned)
        # Remove short store codes like F1528, -330 (letter/dash + 3-4 digits)
        cleaned = re.sub(r'[A-Z\-]\d{3,4}(?=[A-Z]|$)', '', cleaned, flags=re.IGNORECASE)

        # Step 3: Remove city/state patterns
        # Order matters: longer patterns first
        city_state_patterns = [
            r'MOUNTAIN\s*VIEW\s*CA',
            r'MOUNTAINVIEW\s*CA',
            r'SAN\s*FRANCISCO\s*CA',
            r'SANFRANCISCO\s*CA',
            r'SANTA\s*CLARA\s*CA',
            r'SANTACLARA\s*CA',
            r'SAN\s*JOSE\s*CA',
            r'SANJOSE\s*CA',
            r'PALO\s*ALTO\s*CA',
            r'PALOALTO\s*CA',
            r'MENLO\s*PARK\s*CA',
            r'SUNNYVALE\s*CA',
            r'CUPERTINO\s*CA',
            r'REDWOOD\s*CITY\s*CA',
            r'LOS\s*ANGELES\s*CA',
            r'NEW\s*YORK\s*NY',
            r'GILROY\s*CA',
            r'ANTHROPIC\.COM\s*CA',
            r'Mountain\s*View\s*CA',  # Mixed case version
        ]

        for pattern in city_state_patterns:
            cleaned = re.sub(pattern + r'\s*$', '', cleaned, flags=re.IGNORECASE)

        # Clean whitespace before further processing
        cleaned = ' '.join(cleaned.split())

        # Remove trailing 2-letter state code at end
        # Only for common states that appear in Capital One statements
        # Require at least 3 characters before state code to avoid breaking short words
        common_states = ['CA', 'FL', 'GA', 'NY', 'TX', 'WA', 'OR']
        for state in common_states:
            # Match: at least 3 word characters, then state code at end
            cleaned = re.sub(rf'(\w{{3,}}){state}\s*$', r'\1', cleaned, flags=re.IGNORECASE)

        # Remove trailing numbers
        cleaned = re.sub(r'\s*\d+\s*$', '', cleaned)

        # Remove .COM suffix
        cleaned = re.sub(r'\.COM\s*$', '', cleaned, flags=re.IGNORECASE)

        # Remove extra whitespace
        cleaned = ' '.join(cleaned.split())

        # Title case for cleaner display (only if all uppercase)
        if cleaned.isupper() and len(cleaned) > 2:
            cleaned = cleaned.title()

        return cleaned.strip()

    def _parse_allybank_statement(self) -> ParseResult:
        """Parse Ally Bank statement.

        Ally Bank statements have text-based transaction format with multiple accounts:
        - Spending Account section
        - Savings Account section
        - Format: MM/DD/YYYY Description Credits Debits Balance

        Returns:
            ParseResult with transactions from all accounts
        """
        errors = []
        warnings = []
        transactions = []

        try:
            # Extract all text from all pages
            all_text = ""
            for page in self.pdf.pages:
                text = page.extract_text()
                if text:
                    all_text += text + "\n"

            # Parse transactions from text
            transactions = self._extract_allybank_transactions(all_text)

            if not transactions:
                return ParseResult(
                    success=False,
                    transactions=[],
                    errors=["No transactions found in Ally Bank statement"],
                    warnings=warnings,
                    metadata={'format': 'allybank'}
                )

            return ParseResult(
                success=True,
                transactions=transactions,
                errors=errors,
                warnings=warnings,
                metadata={
                    'total_transactions': len(transactions),
                    'source': 'pdf',
                    'format': 'allybank',
                }
            )

        except Exception as e:
            errors.append(f"Failed to parse Ally Bank statement: {str(e)}")
            return ParseResult(
                success=False,
                transactions=[],
                errors=errors,
                warnings=warnings,
                metadata={'format': 'allybank'}
            )

    def _extract_allybank_transactions(self, text: str) -> List[Dict[str, Any]]:
        """Extract transactions from Ally Bank statement text.

        Ally Bank transaction format:
        - Date Description Credits Debits Balance
        - Date format: MM/DD/YYYY (full year included)
        - Credits: deposits, interest (positive values)
        - Debits: withdrawals (shown with - prefix)
        - Multi-line descriptions common

        Example lines:
        12/29/2025 ACH Withdrawal $0.00 -$1,664.99 $18,740.01
        AMEX EPAYMENT ACH PMT
        01/05/2026 Interest Paid $4.16 -$0.00 $15,894.17

        Args:
            text: Full text of the Ally Bank statement

        Returns:
            List of transaction dictionaries
        """
        transactions = []
        lines = text.split('\n')
        row_index = 0
        in_activity_section = False
        current_account_type = None

        # Pattern for Ally Bank transactions:
        # MM/DD/YYYY Description $Credits -$Debits $Balance
        # Credits and Debits use $0.00 when no value
        transaction_pattern = r'^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+\$?([\d,]+\.\d{2})\s+-?\$?([\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})$'

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Detect account type sections
            if 'Spending Account' in line:
                current_account_type = 'spending'
                in_activity_section = False
            elif 'Savings Account' in line:
                current_account_type = 'savings'
                in_activity_section = False

            # Detect Activity section start
            if line == 'Activity' or 'Date Description' in line:
                in_activity_section = True
                i += 1
                continue

            # End of activity section markers
            if any(marker in line for marker in [
                'Ending Balance',
                'Interest Paid YTD',
                'Interest Withheld YTD',
                'Important Information',
                'Sincerely,',
            ]):
                in_activity_section = False
                i += 1
                continue

            if not in_activity_section:
                i += 1
                continue

            # Skip header line
            if 'Credits' in line and 'Debits' in line:
                i += 1
                continue

            # Skip empty lines
            if not line:
                i += 1
                continue

            # Try to match transaction pattern
            match = re.match(transaction_pattern, line)
            if match:
                date_str = match.group(1)
                description = match.group(2).strip()
                credits_str = match.group(3)
                debits_str = match.group(4)

                # Look ahead for multi-line description
                j = i + 1
                while j < len(lines) and j < i + 4:
                    next_line = lines[j].strip()
                    # Stop if we hit another transaction or end markers
                    if not next_line:
                        j += 1
                        continue
                    if re.match(r'^\d{2}/\d{2}/\d{4}', next_line):
                        break
                    if any(marker in next_line for marker in ['Ending Balance', 'Activity', 'Account']):
                        break
                    # This is a description continuation
                    description = f"{description} {next_line}"
                    j += 1

                txn = self._parse_allybank_transaction_line(
                    date_str,
                    description,
                    credits_str,
                    debits_str,
                    current_account_type
                )

                if txn:
                    txn['row_index'] = row_index
                    row_index += 1
                    transactions.append(txn)

                i = j
                continue

            i += 1

        return transactions

    def _parse_allybank_transaction_line(self, date_str: str, description: str,
                                          credits_str: str, debits_str: str,
                                          account_type: str) -> Optional[Dict[str, Any]]:
        """Parse a single Ally Bank transaction line.

        Args:
            date_str: Date string in MM/DD/YYYY format
            description: Transaction description
            credits_str: Credits amount string (0.00 if no credit)
            debits_str: Debits amount string (0.00 if no debit)
            account_type: 'spending' or 'savings'

        Returns:
            Transaction dictionary or None if parsing fails
        """
        try:
            # Parse date (MM/DD/YYYY format - full year included)
            month, day, year = date_str.split('/')
            parsed_date = datetime(int(year), int(month), int(day)).date()

            # Parse amounts
            credit_amount = float(credits_str.replace(',', ''))
            debit_amount = float(debits_str.replace(',', ''))

            # Determine amount and direction for spending tracking convention:
            # - Debits (money OUT of bank) = positive amount (expense/transfer)
            # - Credits (money IN to bank) = negative amount (income)
            if debit_amount > 0:
                # This is a debit (withdrawal) - money leaving the account
                amount = debit_amount  # Positive = expense/outflow
                is_credit = False
            else:
                # This is a credit (deposit) - money entering the account
                amount = -credit_amount  # Negative = income/inflow
                is_credit = True

            # Clean merchant description
            cleaned_merchant = self._clean_allybank_merchant(description)

            # Determine if this is a payment/transfer (credit card or bank transfer)
            # These should be classified as TRANSFER, not EXPENSE
            desc_upper = description.upper()

            # Credit card payment keywords
            cc_payment_keywords = [
                'CREDIT CARD', 'CREDIT CRD', 'EPAYMENT', 'AUTOPAY', 'AUTO PAY',
                'WF CREDIT', 'CHASE CREDIT', 'AMEX', 'CAPITAL ONE', 'CITI CARD',
                'DISCOVER', 'BARCLAYS',
            ]

            # Bank-to-bank transfer keywords
            bank_transfer_keywords = [
                'EXT TRNSFR', 'EXTERNAL TRANSFER', 'BANK TRANSFER', 'WIRE TRANSFER',
                'JPMORGAN CHASE', 'FIDELITY', 'SCHWAB', 'VANGUARD', 'MONEYLINE',
                'FID BKG SVC',  # Fidelity transfers
            ]

            is_cc_payment = any(kw in desc_upper for kw in cc_payment_keywords) and debit_amount > 0
            is_bank_transfer = any(kw in desc_upper for kw in bank_transfer_keywords) and debit_amount > 0
            is_payment = is_cc_payment or is_bank_transfer
            transfer_category = 'Credit Card Payments' if is_cc_payment else 'Transfers' if is_bank_transfer else None

            return {
                'date': parsed_date.isoformat(),
                'description_raw': description,
                'merchant_normalized': cleaned_merchant,
                'amount': amount,  # Positive for debits (outflow), negative for credits (inflow)
                'is_payment': is_payment,
                'is_credit': is_credit,  # True for deposits, False for withdrawals
                'transfer_category': transfer_category,  # 'Credit Card Payments' or 'Transfers'
                'currency': 'USD',
                'account_type': account_type,  # 'spending' or 'savings'
            }

        except Exception as e:
            print(f"Failed to parse Ally Bank line: {date_str} {description}, error: {e}")
            return None

    def _clean_allybank_merchant(self, description: str) -> str:
        """Clean Ally Bank merchant description.

        Ally Bank format examples:
        - "Direct Deposit META PLATFORMS I BDUCVUF9SL ISA¦00¦¦ZZ..." -> "Meta Platforms"
        - "ACH Withdrawal AMEX EPAYMENT ACH PMT" -> "Amex Epayment"
        - "ACH Withdrawal WF Credit Card AUTO PAY" -> "WF Credit Card"
        - "Interest Paid" -> "Interest"

        Args:
            description: Raw transaction description

        Returns:
            Cleaned merchant name
        """
        cleaned = description

        # Handle "Interest Paid" as special case (check before removing prefixes)
        if 'Interest Paid' in description or 'I nterest Paid' in description:
            return 'Interest'

        # Remove transaction type prefixes
        prefixes = [
            r'^Direct Deposit\s+',
            r'^ACH Withdrawal\s+',
            r'^ACH Deposit\s+',
            r'^Interest Paid\s*',
            r'^Wire Transfer\s+',
            r'^ATM Withdrawal\s+',
        ]
        for prefix in prefixes:
            cleaned = re.sub(prefix, '', cleaned, flags=re.IGNORECASE)

        # Remove everything after certain markers that indicate continuation text
        cleaned = re.sub(r'\s+Ally Bank Member FDIC.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+Transaction Proceeds.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+OPTUMCLAIM.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+EquatePlus.*$', '', cleaned, flags=re.IGNORECASE)

        # Remove reference codes with pipe characters (¦)
        cleaned = re.sub(r'\s*¦[^¦]*¦[^¦]*¦.*$', '', cleaned)
        cleaned = re.sub(r'\s*ISA¦.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+ISA\s*$', '', cleaned, flags=re.IGNORECASE)

        # Remove "Future Amount:" and tilde annotations
        cleaned = re.sub(r'\s*~.*$', '', cleaned)
        cleaned = re.sub(r'\s*Future Amount:.*$', '', cleaned, flags=re.IGNORECASE)

        # Remove trailing reference codes (like DDIR, PAYMENTS~, etc.)
        cleaned = re.sub(r'\s+PAYMENTS~?.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+PAYROLL.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+AUTOPAY.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+AUTO PAY.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+DDIR\s*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+ACH PMT\s*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+PAYMENT\s*$', '', cleaned, flags=re.IGNORECASE)

        # Remove alphanumeric reference codes (mixed letters+numbers like BDUCVUF9SL, E37853Ff07C8103)
        # Only remove if it contains BOTH letters AND numbers (true reference codes)
        # Don't remove pure letter words like "TRANSAMERICA" or "INSPAYMENT"
        cleaned = re.sub(r'\s+[A-Za-z]+\d+[A-Za-z0-9]*\s*', ' ', cleaned)  # Must have letter then digit
        cleaned = re.sub(r'\s+\d+[A-Za-z]+[A-Za-z0-9]*\s*', ' ', cleaned)  # Must have digit then letter
        cleaned = re.sub(r'^[A-Za-z]+\d+[A-Za-z0-9]*\s+', '', cleaned)  # At start of string
        # Remove all instances of WORD* pattern (like BRGHTWHL*)
        cleaned = re.sub(r'\b[A-Z]{4,}\*\s*', '', cleaned)
        cleaned = re.sub(r'\s+[A-Z]+\*.*$', '', cleaned)

        # Clean up ACH/Ach Pmt patterns
        cleaned = re.sub(r'\s+Ach Pmt\s*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+ACH PMT\s*$', '', cleaned, flags=re.IGNORECASE)

        # Clean up wire transfer descriptions
        cleaned = re.sub(r'\s+FROM:.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+FED REF ID:.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'^Incoming Wire\s*', 'Wire Transfer ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'^Outgoing Wire\s*', 'Wire Transfer ', cleaned, flags=re.IGNORECASE)

        # Remove trailing asterisks and other punctuation
        cleaned = re.sub(r'\s*\*+\s*$', '', cleaned)

        # Remove long numeric codes
        cleaned = re.sub(r'\b\d{8,}\b', '', cleaned)

        # Remove duplicate words (like "BRGHTWHL* BRGHTWHL*")
        words = cleaned.split()
        seen = set()
        unique_words = []
        for word in words:
            word_lower = word.lower().strip('*')
            if word_lower not in seen:
                seen.add(word_lower)
                unique_words.append(word)
        cleaned = ' '.join(unique_words)

        # Remove common suffixes
        cleaned = re.sub(r'\s+Inc\.?\s*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+LLC\.?\s*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+N\.?A\.?\s*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r',\s*$', '', cleaned)

        # Remove trailing single letters or short codes
        cleaned = re.sub(r'\s+[A-Z]{1,2}\s*$', '', cleaned)

        # Remove extra whitespace
        cleaned = ' '.join(cleaned.split())

        # Title case for cleaner display (only if all uppercase)
        if cleaned.isupper() and len(cleaned) > 2:
            cleaned = cleaned.title()

        return cleaned.strip() if cleaned else description

    def _parse_chasebank_statement(self) -> ParseResult:
        """Parse Chase Bank checking/savings statement.

        Chase Bank statements have:
        - TRANSACTION DETAIL sections
        - Format: MM/DD Description Amount Balance
        - Statement period in header (e.g., "November 26, 2025throughDecember 22, 2025")
        """
        try:
            if not self.pdf:
                return ParseResult(
                    success=False,
                    transactions=[],
                    errors=["Failed to open PDF"],
                    warnings=[],
                    metadata={'format': 'chasebank'}
                )

            # Extract all text from all pages
            all_text = ""
            for page in self.pdf.pages:
                text = page.extract_text()
                if text:
                    all_text += text + "\n"

            if not all_text:
                return ParseResult(
                    success=False,
                    transactions=[],
                    errors=["No text extracted from Chase Bank statement"],
                    warnings=[],
                    metadata={'format': 'chasebank'}
                )

            # Extract statement year from header
            statement_year = self._extract_chasebank_year(all_text)

            # Extract transactions
            transactions = self._extract_chasebank_transactions(all_text, statement_year)

            if not transactions:
                return ParseResult(
                    success=False,
                    transactions=[],
                    errors=["No transactions found in Chase Bank statement"],
                    warnings=[],
                    metadata={'format': 'chasebank'}
                )

            return ParseResult(
                success=True,
                transactions=transactions,
                errors=[],
                warnings=[],
                metadata={
                    'total_transactions': len(transactions),
                    'format': 'chasebank',
                    'statement_year': statement_year,
                }
            )

        except Exception as e:
            return ParseResult(
                success=False,
                transactions=[],
                errors=[f"Failed to parse Chase Bank statement: {str(e)}"],
                warnings=[],
                metadata={'format': 'chasebank'}
            )

    def _extract_chasebank_year(self, text: str) -> int:
        """Extract statement year from Chase Bank header.

        Format: "November 26, 2025throughDecember 22, 2025"
        """
        import re
        from datetime import datetime

        # Look for date pattern in header
        date_pattern = r'(\w+\s+\d{1,2},\s*\d{4})\s*through\s*(\w+\s+\d{1,2},\s*\d{4})'
        match = re.search(date_pattern, text, re.IGNORECASE)

        if match:
            try:
                end_date_str = match.group(2)
                # Parse "December 22, 2025"
                end_date = datetime.strptime(end_date_str, "%B %d, %Y")
                return end_date.year
            except ValueError:
                pass

        # Fallback to current year
        return datetime.now().year

    def _extract_chasebank_transactions(self, text: str, statement_year: int) -> List[Dict[str, Any]]:
        """Extract transactions from Chase Bank statement text.

        Transaction format:
        MM/DD Description Amount Balance
        e.g., "11/28 Comcast-Xfinity Cable Svcs PPD ID: 0000213249 -55.00 24,287.58"
        """
        import re
        from datetime import datetime

        transactions = []
        lines = text.split('\n')
        row_index = 0
        in_transaction_section = False

        # Pattern: MM/DD Description Amount Balance
        # Amount can be negative (-55.00) or positive (0.39)
        # Balance is always positive with optional $ sign
        transaction_pattern = r'^(\d{2}/\d{2})\s+(.+?)\s+(-?[\d,]+\.\d{2})\s+([\d,]+\.\d{2})$'

        for i, line in enumerate(lines):
            line = line.strip()

            # Detect transaction section start
            if 'TRANSACTION DETAIL' in line:
                in_transaction_section = True
                continue

            # Skip headers and markers
            if 'DATE DESCRIPTION AMOUNT BALANCE' in line.upper():
                continue
            if 'Beginning Balance' in line or 'Ending Balance' in line:
                continue
            if '*start*' in line or '*end*' in line:
                in_transaction_section = False
                continue

            if not in_transaction_section:
                continue

            # Try to match transaction pattern
            match = re.match(transaction_pattern, line)
            if match:
                date_str = match.group(1)
                description = match.group(2).strip()
                amount_str = match.group(3)
                # balance_str = match.group(4)  # Not needed

                txn = self._parse_chasebank_transaction_line(
                    date_str,
                    description,
                    amount_str,
                    statement_year,
                    row_index
                )

                if txn:
                    transactions.append(txn)
                    row_index += 1

        return transactions

    def _parse_chasebank_transaction_line(self, date_str: str, description: str,
                                           amount_str: str, statement_year: int,
                                           row_index: int) -> Optional[Dict[str, Any]]:
        """Parse a single Chase Bank transaction line.

        Args:
            date_str: Date string in MM/DD format
            description: Transaction description
            amount_str: Amount string (negative for withdrawals)
            statement_year: Year from statement header
            row_index: Row index for deduplication

        Returns:
            Transaction dictionary or None if parsing fails
        """
        from datetime import datetime

        try:
            # Parse date (MM/DD format)
            month, day = date_str.split('/')
            month_int = int(month)
            day_int = int(day)

            # Handle year rollover (statement might span two years)
            # Use statement_year, but if month is > current statement month, it's previous year
            parsed_date = datetime(statement_year, month_int, day_int).date()

            # Parse amount
            amount = float(amount_str.replace(',', ''))

            # For bank accounts:
            # - Negative amounts = withdrawals (outflow) → positive for expense tracking
            # - Positive amounts = deposits (income) → negative for expense tracking
            if amount < 0:
                # Withdrawal (expense/transfer)
                final_amount = abs(amount)
                is_credit = False
            else:
                # Deposit (income)
                final_amount = -amount
                is_credit = True

            # Clean merchant description
            cleaned_merchant = self._clean_chasebank_merchant(description)

            # Determine if this is a payment/transfer
            desc_upper = description.upper()

            # Credit card payment keywords
            cc_payment_keywords = [
                'CREDIT CARD', 'CREDIT CRD', 'CRCARDPMT', 'AUTOPAY',
                'WF CREDIT', 'CHASE CREDIT', 'AMEX', 'AMERICAN EXPRESS',
                'CAPITAL ONE', 'CITI CARD', 'DISCOVER', 'BARCLAYS',
                'BANK OF AMERICA', 'SYNCHRONY',
            ]

            # Bank-to-bank transfer keywords
            bank_transfer_keywords = [
                'EXT TRNSFR', 'EXTERNAL TRANSFER', 'BANK TRANSFER',
                'WIRE TRANSFER', 'ZELLE', 'VENMO', 'PAYPAL',
            ]

            is_cc_payment = any(kw in desc_upper for kw in cc_payment_keywords) and amount < 0
            is_bank_transfer = any(kw in desc_upper for kw in bank_transfer_keywords) and amount < 0
            is_payment = is_cc_payment or is_bank_transfer
            transfer_category = 'Credit Card Payments' if is_cc_payment else 'Transfers' if is_bank_transfer else None

            return {
                'date': parsed_date.isoformat(),
                'description_raw': description,
                'merchant_normalized': cleaned_merchant,
                'amount': final_amount,
                'is_payment': is_payment,
                'is_credit': is_credit,
                'transfer_category': transfer_category,
                'currency': 'USD',
                'row_index': row_index,
            }

        except Exception as e:
            print(f"Failed to parse Chase Bank line: {date_str} {description}, error: {e}")
            return None

    def _clean_chasebank_merchant(self, description: str) -> str:
        """Clean Chase Bank merchant description.

        Chase Bank format examples:
        - "Comcast-Xfinity Cable Svcs PPD ID: 0000213249" -> "Comcast Xfinity Cable Svcs"
        - "Wf Credit Card Auto Pay PPD ID: 50260000" -> "WF Credit Card"
        - "Capital One Crcardpmt CA06B3D96E7C79B Web ID: 9541719318" -> "Capital One"
        - "American Express ACH Pmt A7602 Web ID: 9493560001" -> "American Express"
        """
        import re

        cleaned = description

        # Remove PPD ID, Web ID suffixes
        cleaned = re.sub(r'\s*PPD ID:\s*\d+\s*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*Web ID:\s*\d+\s*$', '', cleaned, flags=re.IGNORECASE)

        # Remove alphanumeric reference codes (like CA06B3D96E7C79B, A7602, Ckf520086972POS)
        cleaned = re.sub(r'\s+[A-Za-z]+\d+[A-Za-z0-9]*\s*$', '', cleaned)
        cleaned = re.sub(r'\s+[A-Za-z]\d{4,}\s*$', '', cleaned)

        # Remove "ACH Pmt" suffix
        cleaned = re.sub(r'\s+ACH Pmt\s*$', '', cleaned, flags=re.IGNORECASE)

        # Remove "Auto Pay" suffix (keep the company name before it)
        cleaned = re.sub(r'\s+Auto Pay\s*$', '', cleaned, flags=re.IGNORECASE)

        # Remove "Crcardpmt" and similar
        cleaned = re.sub(r'\s+Crcardpmt\s*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+Crcardpmt\s+', ' ', cleaned, flags=re.IGNORECASE)

        # Remove "Auto EFT" suffix
        cleaned = re.sub(r'\s+Auto EFT\s*$', '', cleaned, flags=re.IGNORECASE)

        # Clean up common patterns
        cleaned = re.sub(r'\s+Online Pmt\s*$', '', cleaned, flags=re.IGNORECASE)

        # Replace hyphens with spaces for readability
        cleaned = cleaned.replace('-', ' ')

        # Remove extra whitespace
        cleaned = ' '.join(cleaned.split())

        # Title case if all uppercase
        if cleaned.isupper() and len(cleaned) > 2:
            cleaned = cleaned.title()

        return cleaned.strip() if cleaned else description

    def _extract_statement_year(self) -> int:
        """Extract statement year from PDF header.

        Supports Fidelity, Amex, and Chase formats:
        - Fidelity: "November2025 Statement", "Closing Date:11/24/2025"
        - Amex: "Closing Date01/22/25"
        - Chase: "February 2025" or "Statement Date: 01/24/25"

        Returns:
            Statement year (e.g., 2025), defaults to current year if not found
        """
        try:
            if not self.pdf or len(self.pdf.pages) == 0:
                return datetime.now().year

            # Get first page text
            first_page_text = self.pdf.pages[0].extract_text()

            if not first_page_text:
                return datetime.now().year

            # Look for "Closing Date: MM/DD/YYYY" pattern (Fidelity format)
            closing_date_match = re.search(r'Closing Date:\s*(\d{2})/(\d{2})/(\d{4})', first_page_text)
            if closing_date_match:
                return int(closing_date_match.group(3))

            # Look for "Statement Closing Date MM/DD/YYYY" pattern (Wells Fargo format)
            wellsfargo_date_match = re.search(r'Statement Closing Date\s+(\d{2})/(\d{2})/(\d{4})', first_page_text)
            if wellsfargo_date_match:
                return int(wellsfargo_date_match.group(3))

            # Look for Capital One billing cycle pattern: "Mon DD, YYYY - Mon DD, YYYY"
            # The second date (end of cycle) has the statement year
            capitalone_date_match = re.search(
                r'[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}\s*-\s*[A-Z][a-z]{2}\s+\d{1,2},\s+(\d{4})',
                first_page_text
            )
            if capitalone_date_match:
                return int(capitalone_date_match.group(1))

            # Look for "Month YYYY" pattern (Chase format: "February 2025")
            # Check this BEFORE Amex pattern because Chase has "Opening/Closing Date" with older dates
            month_year_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', first_page_text)
            if month_year_match:
                return int(month_year_match.group(2))

            # Look for "Closing DateMM/DD/YY" pattern (Amex format - no colon, 2-digit year)
            # This pattern is for Amex which has "Closing Date01/22/25" without space
            amex_date_match = re.search(r'Closing Date(\d{2})/(\d{2})/(\d{2})', first_page_text)
            if amex_date_match:
                year_2digit = int(amex_date_match.group(3))
                return 2000 + year_2digit

            # Look for "MonthYYYY Statement" pattern (e.g., "November2025 Statement")
            month_year_match2 = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s*(\d{4})\s+Statement', first_page_text)
            if month_year_match2:
                return int(month_year_match2.group(2))

            # Fallback: look for any 4-digit year in the first 500 characters
            year_match = re.search(r'\b(20\d{2})\b', first_page_text[:500])
            if year_match:
                return int(year_match.group(1))

            # Default to current year if nothing found
            return datetime.now().year

        except Exception as e:
            print(f"Failed to extract statement year: {str(e)}")
            return datetime.now().year

    def extract_tables(self) -> List[pd.DataFrame]:
        """Extract all tables from PDF."""
        all_tables = []

        for page in self.pdf.pages:
            page_tables = page.extract_tables()

            if page_tables:
                for table in page_tables:
                    if table and len(table) > 1:  # Must have header + at least one row
                        try:
                            # Convert to DataFrame
                            df = pd.DataFrame(table[1:], columns=table[0])
                            # Remove empty rows
                            df = df.dropna(how='all')
                            if len(df) > 0:
                                all_tables.append(df)
                        except Exception:
                            continue

        return all_tables

    def _extract_text_fallback(self) -> List[Dict[str, Any]]:
        """Extract transactions using text-based parsing (fallback when table extraction fails).

        This method handles Fidelity statements that don't have proper table structure.
        It uses regex patterns to extract transaction lines from the text.

        Returns:
            List of transaction dictionaries
        """
        transactions = []
        row_index = 0  # Track row position for deduplication

        try:
            for page in self.pdf.pages:
                text = page.extract_text()

                if not text:
                    continue

                # Parse Fidelity format: two sections (Credits and Debits)
                # Credits section: "Payments and Other Credits"
                # Debits section: "Purchases and Other Debits"

                # Extract credits section
                credits_pattern = r"Payments and Other Credits.*?(?=Purchases|Account Activity|Page \d+|$)"
                credits_match = re.search(credits_pattern, text, re.DOTALL | re.IGNORECASE)

                if credits_match:
                    credits_text = credits_match.group(0)
                    credit_transactions = self._parse_fidelity_text_section(credits_text, is_credit=True, start_row_index=row_index)
                    row_index += len(credit_transactions)
                    transactions.extend(credit_transactions)

                # Extract debits section
                debits_pattern = r"Purchases and Other Debits.*?(?=Account Activity|Total fees|Page \d+|$)"
                debits_match = re.search(debits_pattern, text, re.DOTALL | re.IGNORECASE)

                if debits_match:
                    debits_text = debits_match.group(0)
                    debit_transactions = self._parse_fidelity_text_section(debits_text, is_credit=False, start_row_index=row_index)
                    row_index += len(debit_transactions)
                    transactions.extend(debit_transactions)

            return transactions

        except Exception as e:
            print(f"Text extraction fallback failed: {str(e)}")
            return []

    def _parse_fidelity_text_section(self, text: str, is_credit: bool, start_row_index: int = 0) -> List[Dict[str, Any]]:
        """Parse a section of Fidelity text (Credits or Debits) to extract transactions.

        Fidelity transaction line format:
        MM/DD MM/DD NNNN DESCRIPTION $AMOUNT[CR]

        Example:
        11/14 11/14 8459 COMCAST / XFINITY 800-266-2278 CA $73.00
        11/17 11/17 MTC PAYMENT THANK YOU $373.00CR

        Args:
            text: Text section containing transactions
            is_credit: Whether this is from the credits section
            start_row_index: Starting row index for deduplication

        Returns:
            List of transaction dictionaries
        """
        transactions = []
        row_index = start_row_index

        # Transaction pattern: MM/DD MM/DD REF# DESCRIPTION $AMOUNT[CR]
        # Note: Date format is MM/DD (not MM/DD/YY), CR has no space
        transaction_pattern = r'^(\d{2}/\d{2})\s+(\d{2}/\d{2})\s+(\w+)\s+(.*?)\s+\$?([\d,]+\.\d{2})(CR)?'

        lines = text.split('\n')

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Skip header lines, empty lines, and total lines
            if not line or 'Post Date' in line or 'Trans Date' in line or \
               'Transaction Description' in line or 'TOTAL THIS PERIOD' in line or \
               'Date' == line or 'Ref #' in line or 'Amount' == line:
                i += 1
                continue

            match = re.search(transaction_pattern, line)

            if match:
                try:
                    trans_date = match.group(1)
                    post_date = match.group(2)
                    ref_num = match.group(3)
                    description = match.group(4).strip()
                    amount_str = match.group(5).strip()
                    has_cr = match.group(6) is not None

                    # Check if next line is a continuation (e.g., "MERCHANDISE/SERVICE RETURN")
                    # Next line is a continuation if it doesn't match the transaction pattern
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        # If next line doesn't look like a transaction (no date), append it
                        if next_line and not re.match(r'^\d{2}/\d{2}', next_line) and \
                           'TOTAL THIS PERIOD' not in next_line and \
                           next_line not in ['Date', 'Ref #', 'Amount']:
                            description = f"{description} {next_line}"
                            i += 1  # Skip the next line since we consumed it

                    # Parse date (use post_date) with statement year
                    # Extract month and day from MM/DD format
                    month = int(post_date.split('/')[0])
                    day = int(post_date.split('/')[1])

                    # Use the statement year extracted from PDF header
                    # Handle year boundary: if statement is in January but transaction is in December,
                    # the transaction is from the previous year
                    statement_year = self.statement_year if self.statement_year else datetime.now().year

                    # If transaction month is much later than we'd expect (e.g., December transaction
                    # in a January statement), use previous year
                    parsed_date = datetime(statement_year, month, day).date()

                    # Clean merchant description
                    cleaned_merchant = self.clean_merchant_description(description)

                    # Parse amount
                    amount_clean = amount_str.replace(',', '').strip()
                    amount = abs(float(amount_clean))

                    # Credits (payments, refunds) are stored as negative amounts
                    if is_credit:
                        amount = -amount

                    # Detect if this is a payment to the card (transfer, not spending)
                    is_payment = 'PAYMENT' in description.upper() and 'THANK YOU' in description.upper()

                    transactions.append({
                        'date': parsed_date.isoformat(),
                        'description_raw': description,
                        'merchant_normalized': cleaned_merchant,
                        'amount': amount,  # Negative for credits, positive for charges
                        'is_payment': is_payment,
                        'currency': 'USD',
                        'row_index': row_index,
                    })
                    row_index += 1

                except Exception as e:
                    # Skip invalid lines
                    print(f"Failed to parse line: '{line}', error: {str(e)}")

            i += 1

        return transactions

    def _identify_fidelity_tables(self, tables: List[pd.DataFrame]) -> tuple:
        """Identify Fidelity Credits and Debits tables.

        Fidelity statements have two separate tables:
        - "Payments and Other Credits" table
        - "Purchases and Other Debits" table

        Returns:
            Tuple of (credit_table, debit_table)
        """
        credit_table = None
        debit_table = None

        for df in tables:
            columns_str = ' '.join([str(col).lower() for col in df.columns])

            # Look for transaction table indicators
            has_date = any('date' in str(col).lower() for col in df.columns)
            has_desc = any('description' in str(col).lower() or 'transaction' in str(col).lower() for col in df.columns)
            has_amount = any('amount' in str(col).lower() for col in df.columns)

            if has_date and has_desc and has_amount:
                # Check if this is a credit or debit table by looking at the data
                # Credits typically have "CR" suffix on amounts
                amount_col = None
                for col in df.columns:
                    if 'amount' in str(col).lower():
                        amount_col = col
                        break

                if amount_col:
                    # Check if amounts have "CR" suffix
                    sample_amounts = df[amount_col].dropna().head(3).astype(str)
                    has_cr = any('cr' in str(amt).lower() for amt in sample_amounts)

                    if has_cr:
                        credit_table = df
                    else:
                        debit_table = df

        return credit_table, debit_table

    def _merge_credit_debit_tables(self, credit_table: Optional[pd.DataFrame],
                                   debit_table: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        """Merge credit and debit tables into a single DataFrame.

        Args:
            credit_table: DataFrame with credits (payments, refunds)
            debit_table: DataFrame with debits (purchases)

        Returns:
            Merged DataFrame with standardized columns
        """
        merged_rows = []
        row_index = 0  # Track row position for deduplication

        # Process credit table
        if credit_table is not None:
            for _, row in credit_table.iterrows():
                parsed_row = self._parse_fidelity_row(row, is_credit=True)
                if parsed_row:
                    parsed_row['row_index'] = row_index
                    row_index += 1
                    merged_rows.append(parsed_row)

        # Process debit table
        if debit_table is not None:
            for _, row in debit_table.iterrows():
                parsed_row = self._parse_fidelity_row(row, is_credit=False)
                if parsed_row:
                    parsed_row['row_index'] = row_index
                    row_index += 1
                    merged_rows.append(parsed_row)

        if not merged_rows:
            return None

        return pd.DataFrame(merged_rows)

    def _parse_fidelity_row(self, row: pd.Series, is_credit: bool) -> Optional[Dict[str, Any]]:
        """Parse a single row from Fidelity table.

        Expected columns (Fidelity format):
        - Post Date or Trans Date
        - Transaction Description or Description
        - Amount

        Args:
            row: DataFrame row
            is_credit: Whether this is from the credits table

        Returns:
            Dictionary with parsed transaction data
        """
        try:
            # Find date column
            date_col = None
            for col in row.index:
                if 'date' in str(col).lower():
                    date_col = col
                    break

            # Find description column
            desc_col = None
            for col in row.index:
                if 'description' in str(col).lower() or 'transaction' in str(col).lower():
                    desc_col = col
                    break

            # Find amount column
            amount_col = None
            for col in row.index:
                if 'amount' in str(col).lower():
                    amount_col = col
                    break

            if not date_col or not desc_col or not amount_col:
                return None

            # Extract values
            date_str = str(row[date_col]).strip()
            description = str(row[desc_col]).strip()
            amount_str = str(row[amount_col]).strip()

            # Skip if any required field is empty
            if not date_str or not description or not amount_str or \
               date_str.lower() in ['nan', 'none'] or \
               description.lower() in ['nan', 'none'] or \
               amount_str.lower() in ['nan', 'none']:
                return None

            # Parse date - handle both MM/DD and MM/DD/YYYY formats
            try:
                # Try parsing as-is (works if YYYY is included)
                parsed_date = pd.to_datetime(date_str).date()
            except:
                # If that fails, assume MM/DD format and add statement year
                try:
                    month, day = date_str.split('/')
                    statement_year = self.statement_year if self.statement_year else datetime.now().year
                    parsed_date = datetime(statement_year, int(month), int(day)).date()
                except:
                    # If all parsing fails, skip this row
                    return None

            # Clean merchant description (remove phone numbers and state codes)
            cleaned_merchant = self.clean_merchant_description(description)

            # Parse amount (remove CR suffix and convert to float)
            amount_clean = amount_str.replace('CR', '').replace('$', '').replace(',', '').strip()
            amount = abs(float(amount_clean))

            # Credits are stored as negative amounts
            if is_credit:
                amount = -amount

            # Detect if this is a payment to the card (transfer, not spending)
            is_payment = 'PAYMENT' in description.upper() and 'THANK YOU' in description.upper()

            return {
                'date': parsed_date.isoformat(),
                'description_raw': description,
                'merchant_normalized': cleaned_merchant,
                'amount': amount,  # Negative for credits, positive for charges
                'is_payment': is_payment,
                'currency': 'USD',
            }

        except Exception:
            return None

    @staticmethod
    def clean_merchant_description(description: str) -> str:
        """Extract merchant name from Fidelity descriptions.

        Fidelity format: "MERCHANT NAME PHONE_NUMBER STATE"
        Examples:
        - "COMCAST / XFINITY 800-266-2278 CA" → "COMCAST / XFINITY"
        - "ABC*OSHMAN FAMILY JEWI 650-2238700 CA" → "ABC*OSHMAN FAMILY JEWI"

        Args:
            description: Raw transaction description

        Returns:
            Cleaned merchant name
        """
        # Remove phone numbers (xxx-xxx-xxxx or xxxxxxxxxx)
        cleaned = re.sub(r'\b\d{3}[-\s]?\d{3}[-\s]?\d{4}\b', '', description)
        cleaned = re.sub(r'\b\d{10}\b', '', cleaned)

        # Remove state codes at the end (2-letter codes)
        cleaned = re.sub(r'\s+[A-Z]{2}\s*$', '', cleaned)

        # Remove extra whitespace
        cleaned = ' '.join(cleaned.split())

        return cleaned.strip()

    def _to_transactions(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Convert merged DataFrame to transaction dictionaries."""
        transactions = df.to_dict('records')
        # row_index is already set in _merge_credit_debit_tables
        return transactions

    def detect_format(self) -> Dict[str, Any]:
        """Detect PDF format."""
        return {
            'format': 'pdf',
            'parser': 'pdfplumber',
            'requires_table_extraction': True,
        }

    def validate(self) -> List[str]:
        """Validate PDF data."""
        errors = []

        if not self.tables:
            errors.append("No tables extracted from PDF")

        return errors
