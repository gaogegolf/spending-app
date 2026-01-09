"""PDF file parser with support for Fidelity two-table format."""

import pdfplumber
import pandas as pd
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.services.file_parser.base import BaseParser, ParseResult


class PDFParser(BaseParser):
    """Parser for PDF statement files."""

    def __init__(self, file_path: str):
        """Initialize PDF parser.

        Args:
            file_path: Path to PDF file
        """
        self.file_path = file_path
        self.pdf = None
        self.tables = []
        self.statement_year = None  # Extract from PDF header

    def parse(self) -> ParseResult:
        """Parse PDF file and return transactions."""
        errors = []
        warnings = []
        transactions = []

        try:
            self.pdf = pdfplumber.open(self.file_path)

            # Extract statement year from PDF header
            self.statement_year = self._extract_statement_year()

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

    def _extract_statement_year(self) -> int:
        """Extract statement year from PDF header.

        Fidelity statements have formats like:
        - "November2025 Statement"
        - "Closing Date:11/24/2025"

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

            # Look for "Closing Date: MM/DD/YYYY" pattern (most reliable)
            closing_date_match = re.search(r'Closing Date:\s*(\d{2})/(\d{2})/(\d{4})', first_page_text)
            if closing_date_match:
                return int(closing_date_match.group(3))

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
                    credit_transactions = self._parse_fidelity_text_section(credits_text, is_credit=True)
                    transactions.extend(credit_transactions)

                # Extract debits section
                debits_pattern = r"Purchases and Other Debits.*?(?=Account Activity|Total fees|Page \d+|$)"
                debits_match = re.search(debits_pattern, text, re.DOTALL | re.IGNORECASE)

                if debits_match:
                    debits_text = debits_match.group(0)
                    debit_transactions = self._parse_fidelity_text_section(debits_text, is_credit=False)
                    transactions.extend(debit_transactions)

            return transactions

        except Exception as e:
            print(f"Text extraction fallback failed: {str(e)}")
            return []

    def _parse_fidelity_text_section(self, text: str, is_credit: bool) -> List[Dict[str, Any]]:
        """Parse a section of Fidelity text (Credits or Debits) to extract transactions.

        Fidelity transaction line format:
        MM/DD MM/DD NNNN DESCRIPTION $AMOUNT[CR]

        Example:
        11/14 11/14 8459 COMCAST / XFINITY 800-266-2278 CA $73.00
        11/17 11/17 MTC PAYMENT THANK YOU $373.00CR

        Args:
            text: Text section containing transactions
            is_credit: Whether this is from the credits section

        Returns:
            List of transaction dictionaries
        """
        transactions = []

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

                    transactions.append({
                        'date': parsed_date.isoformat(),
                        'description_raw': description,
                        'merchant_normalized': cleaned_merchant,
                        'amount': amount,
                        'is_credit': is_credit,
                        'currency': 'USD',
                    })

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

        # Process credit table
        if credit_table is not None:
            for _, row in credit_table.iterrows():
                parsed_row = self._parse_fidelity_row(row, is_credit=True)
                if parsed_row:
                    merged_rows.append(parsed_row)

        # Process debit table
        if debit_table is not None:
            for _, row in debit_table.iterrows():
                parsed_row = self._parse_fidelity_row(row, is_credit=False)
                if parsed_row:
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

            return {
                'date': parsed_date.isoformat(),
                'description_raw': description,
                'merchant_normalized': cleaned_merchant,
                'amount': amount,
                'is_credit': is_credit,
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
