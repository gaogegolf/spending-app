"""PDF file parser with support for Fidelity and American Express formats."""

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
            'amex' for American Express, 'fidelity' for Fidelity, 'unknown' otherwise
        """
        try:
            if not self.pdf or len(self.pdf.pages) == 0:
                return 'unknown'

            # Get first page text
            first_page_text = self.pdf.pages[0].extract_text()

            if not first_page_text:
                return 'unknown'

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

    def _extract_statement_year(self) -> int:
        """Extract statement year from PDF header.

        Supports both Fidelity and Amex formats:
        - Fidelity: "November2025 Statement", "Closing Date:11/24/2025"
        - Amex: "Closing Date01/22/25"

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

            # Look for "Closing DateMM/DD/YY" pattern (Amex format - no colon, 2-digit year)
            amex_date_match = re.search(r'Closing Date\s*(\d{2})/(\d{2})/(\d{2})', first_page_text)
            if amex_date_match:
                year_2digit = int(amex_date_match.group(3))
                return 2000 + year_2digit

            # Look for "MonthYYYY Statement" pattern (e.g., "November2025 Statement")
            month_year_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s*(\d{4})\s+Statement', first_page_text)
            if month_year_match:
                return int(month_year_match.group(2))

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
