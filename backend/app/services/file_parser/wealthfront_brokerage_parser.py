"""Wealthfront brokerage statement parser."""

import re
from typing import List, Optional, Tuple
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import pdfplumber

from app.services.file_parser.brokerage_parser import (
    BaseBrokerageParser,
    BrokerageParseResult,
    PositionData,
    detect_account_type,
)


class WealthfrontBrokerageParser(BaseBrokerageParser):
    """Parser for Wealthfront brokerage statements.

    Supports Wealthfront monthly PDF statements with holdings tables
    for ETFs/Stocks, Money Market Funds, and Cash positions.
    """

    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.provider = "wealthfront"

    def parse(self) -> BrokerageParseResult:
        """Parse Wealthfront statement and return holdings snapshot."""
        errors = []
        warnings = []

        try:
            self._open_pdf()

            # Detect account type
            self.account_type = self.detect_account_type()

            # Extract data
            account_id = self._extract_account_identifier()
            statement_date, statement_start_date = self._extract_statement_dates()
            total_value, total_cash, total_securities = self._extract_totals()
            positions = self._extract_positions()

            # Calculate total from positions for reconciliation
            calculated_total = self._calculate_total(positions)
            is_reconciled, reconciliation_diff = self._reconcile(total_value, calculated_total)

            if not is_reconciled:
                warnings.append(
                    f"Reconciliation warning: calculated total ${calculated_total} differs from "
                    f"reported total ${total_value} by ${reconciliation_diff}"
                )

            return BrokerageParseResult(
                success=True,
                provider=self.provider,
                account_type=self.account_type,
                account_identifier=account_id,
                statement_date=statement_date,
                statement_start_date=statement_start_date,
                total_value=total_value,
                total_cash=total_cash,
                total_securities=total_securities,
                positions=positions,
                calculated_total=calculated_total,
                is_reconciled=is_reconciled,
                reconciliation_diff=reconciliation_diff,
                errors=errors,
                warnings=warnings,
                raw_metadata={
                    "pages": len(self.pdf.pages) if self.pdf else 0,
                    "position_count": len(positions),
                },
            )

        except Exception as e:
            errors.append(f"Failed to parse Wealthfront statement: {str(e)}")
            return BrokerageParseResult(
                success=False,
                provider=self.provider,
                account_type=self.account_type or "BROKERAGE",
                account_identifier="",
                statement_date=None,
                statement_start_date=None,
                total_value=Decimal("0"),
                total_cash=Decimal("0"),
                total_securities=Decimal("0"),
                positions=[],
                calculated_total=Decimal("0"),
                is_reconciled=False,
                reconciliation_diff=Decimal("0"),
                errors=errors,
                warnings=warnings,
            )
        finally:
            self._close_pdf()

    def detect_account_type(self) -> str:
        """Detect account type from Wealthfront statement."""
        if not self.full_text:
            self._open_pdf()

        text_lower = self.full_text.lower()

        # Check for IRA types first
        if "roth ira" in text_lower or "roth individual" in text_lower:
            return "IRA_ROTH"
        if "traditional ira" in text_lower or "rollover ira" in text_lower:
            return "IRA_TRADITIONAL"

        # Joint account detection
        if "joint" in text_lower:
            return "BROKERAGE"

        # Default to brokerage for taxable accounts
        return "BROKERAGE"

    def _extract_account_identifier(self) -> str:
        """Extract masked account identifier from Wealthfront statement.

        Wealthfront account numbers are 8-character alphanumeric codes.
        Format varies by statement date:
        - Newer statements: "ACCOUNT NUMBERS\nWealthfront: 8W15S8CW"
        - Older statements: Account number on its own line after "JTWROS1"
        """
        # Look for "Wealthfront: XXXXXXXX" pattern (newer statements)
        wf_pattern = r"Wealthfront:\s*([A-Z0-9]{8})\b"
        match = re.search(wf_pattern, self.full_text)
        if match:
            account_num = match.group(1)
            return f"****{account_num[-4:]}"

        # Pattern: 8-character alphanumeric code after ACCOUNT NUMBERS (newer statements)
        account_section_pattern = r"ACCOUNT\s+NUMBERS?\s*[\n\r]+(?:Wealthfront:\s*)?([A-Z0-9]{8})"
        match = re.search(account_section_pattern, self.full_text, re.IGNORECASE)
        if match:
            account_num = match.group(1)
            return f"****{account_num[-4:]}"

        # Older format: Account number appears after JTWROS line
        # Pattern: "JTWROS1" followed by account number on next line or same line
        jtwros_pattern = r"JTWROS\d?\s*(?:Apt\s+\d+)?\s*\n?\s*([A-Z0-9]{8})\b"
        match = re.search(jtwros_pattern, self.full_text)
        if match:
            account_num = match.group(1)
            return f"****{account_num[-4:]}"

        # Fallback: Look for 8-char alphanumeric that matches Wealthfront account pattern
        # (starts with digit or letter, contains mix of both)
        # Search in first 1500 chars (page 1) to avoid matching CUSIPs
        first_page = self.full_text[:1500]
        account_pattern = r"\b([0-9][A-Z0-9]{7}|[A-Z][0-9A-Z]{7})\b"
        matches = re.findall(account_pattern, first_page)
        for m in matches:
            # Must have both letters and numbers (not pure numeric like CUSIPs)
            if re.search(r'[A-Z]', m) and re.search(r'[0-9]', m):
                return f"****{m[-4:]}"

        return "Unknown"

    def _extract_statement_dates(self) -> Tuple[Optional[date], Optional[date]]:
        """Extract statement date range from Wealthfront statement.

        Looks for patterns like:
        - "Monthly Statement for December 1 - 31, 2025"
        """
        # Pattern: "Monthly Statement for Month D - D, YYYY"
        date_pattern = r"Monthly\s+Statement\s+for\s+(\w+)\s+(\d{1,2})\s*[-–]\s*(\d{1,2}),?\s+(\d{4})"
        match = re.search(date_pattern, self.full_text, re.IGNORECASE)

        if match:
            month_str = match.group(1)
            start_day = int(match.group(2))
            end_day = int(match.group(3))
            year = int(match.group(4))

            try:
                # Parse month name
                month_date = datetime.strptime(month_str, "%B")
                month = month_date.month

                start_date = date(year, month, start_day)
                end_date = date(year, month, end_day)
                return end_date, start_date
            except ValueError:
                pass

        # Alternative pattern: "Statement Period: Month D - Month D, YYYY"
        alt_pattern = r"Statement\s+Period[:\s]+(\w+\s+\d{1,2})\s*[-–]\s*(\w+\s+\d{1,2}),?\s+(\d{4})"
        match = re.search(alt_pattern, self.full_text, re.IGNORECASE)

        if match:
            try:
                start_str = f"{match.group(1)}, {match.group(3)}"
                end_str = f"{match.group(2)}, {match.group(3)}"
                start_date = datetime.strptime(start_str, "%B %d, %Y").date()
                end_date = datetime.strptime(end_str, "%B %d, %Y").date()
                return end_date, start_date
            except ValueError:
                pass

        return None, None

    def _extract_totals(self) -> Tuple[Decimal, Decimal, Decimal]:
        """Extract total values from Wealthfront statement.

        Looks for:
        - Total Holdings value (most reliable)
        - Ending Balance on page 1
        """
        total_value = Decimal("0")
        total_cash = Decimal("0")
        total_securities = Decimal("0")

        # Pattern for Total Holdings (most reliable, appears after all holdings)
        total_holdings_pattern = r"Total\s+Holdings\s+\$?([\d,]+\.?\d*)"
        match = re.search(total_holdings_pattern, self.full_text, re.IGNORECASE)
        if match:
            try:
                total_value = Decimal(match.group(1).replace(",", ""))
            except InvalidOperation:
                pass

        # Fallback: Pattern for Ending Balance
        if total_value == 0:
            ending_balance_patterns = [
                r"Ending\s+Balance\s+\$?([\d,]+\.?\d*)",
                r"Account\s+Value[:\s]*\$?([\d,]+\.?\d*)",
            ]

            for pattern in ending_balance_patterns:
                match = re.search(pattern, self.full_text, re.IGNORECASE)
                if match:
                    try:
                        total_value = Decimal(match.group(1).replace(",", ""))
                        break
                    except InvalidOperation:
                        continue

        # Extract cash from the CASH section - look for "US Dollar $X.XX" or "Total $X.XX" in CASH section
        # Find the CASH section and extract the value
        cash_section_pattern = r"CASH\s+Currency\s+Value\s+US\s+Dollar\s+\$?([\d,]+\.?\d*)"
        match = re.search(cash_section_pattern, self.full_text, re.IGNORECASE)
        if match:
            try:
                total_cash = Decimal(match.group(1).replace(",", ""))
            except InvalidOperation:
                pass

        # Calculate securities as total minus cash
        total_securities = total_value - total_cash

        return total_value, total_cash, total_securities

    def _extract_positions(self) -> List[PositionData]:
        """Extract position/holdings data from Wealthfront statement.

        Wealthfront statements have holdings tables with columns:
        - Security (name)
        - Symbol/CUSIP
        - Shares
        - Share Price
        - Value

        Categories include: ETFs/STOCKS, MONEY MARKET FUNDS, OTHER, CASH
        Only extracts from "I. Holdings" section, stops at "II. Account Activity"
        """
        positions = []
        row_index = 0

        # Extract holdings section text only (stop at Account Activity)
        holdings_text = self._extract_holdings_section()

        # Parse holdings from text
        positions = self._parse_holdings_text(holdings_text)

        return positions

    def _extract_holdings_section(self) -> str:
        """Extract only the Holdings section text, stopping at Account Activity.

        Wealthfront statements have:
        - Page 1: Summary with "I. Holdings" and "II. Account Activity" as headers
        - Pages 2+: Detailed "I. Holdings as of [date]" with actual positions
        - Later pages: "II. Account Activity" section with trades/dividends

        We want the detailed holdings from pages 2+, not the summary on page 1.
        """
        # Look for "Holdings as of" which marks the start of detailed holdings (page 2+)
        holdings_detail_match = re.search(r"Holdings\s+as\s+of", self.full_text, re.IGNORECASE)

        # Look for "Total Holdings" which marks the end of the holdings section
        total_holdings_match = re.search(r"Total\s+Holdings\s+\$[\d,]+\.?\d*", self.full_text)

        # Look for "Account Activity" after holdings (not the summary on page 1)
        # The detailed activity section usually has "TRADES" or "Deposits/Credits"
        activity_detail_match = re.search(r"Deposits/Credits\s+to\s+Wealthfront", self.full_text, re.IGNORECASE)
        if not activity_detail_match:
            activity_detail_match = re.search(r"TRADES\s+Trade\s+Date", self.full_text, re.IGNORECASE)

        if holdings_detail_match:
            start_pos = holdings_detail_match.start()
        else:
            # Fallback: start from beginning
            start_pos = 0

        if total_holdings_match:
            # Include a bit after "Total Holdings" to capture the value
            end_pos = total_holdings_match.end() + 200
        elif activity_detail_match:
            end_pos = activity_detail_match.start()
        else:
            end_pos = len(self.full_text)

        return self.full_text[start_pos:end_pos]

    def _parse_holdings_text(self, text: str) -> List[PositionData]:
        """Parse holdings from the holdings section text."""
        positions = []
        row_index = 0
        lines = text.split('\n')

        # Track current category
        current_category = "ETF"  # Default

        # Pattern for holdings lines
        # Format: Security Name    SYMBOL    Shares    $Price    $Value
        # e.g.: APPLE INC COM AAPL 5.61364 $271.8600 $1,526.12
        # e.g.: RBC US Government Money Market Fund TIMXX 19.46 $1.0000 $19.46
        holdings_pattern = re.compile(
            r'^(.+?)\s+'                    # Security name (non-greedy)
            r'([A-Z][A-Z0-9\.]{0,5})\s+'    # Symbol (1-6 chars, may have dot like BF.B)
            r'([\d,]+\.?\d*)\s+'            # Shares
            r'\$?([\d,]+\.?\d*)\s+'         # Price
            r'\$?([\d,]+\.?\d*)$'           # Value
        )

        # Alternative pattern for securities with CUSIP instead of symbol
        cusip_pattern = re.compile(
            r'^(.+?)\s+'                    # Security name (non-greedy)
            r'([A-Z0-9]{9})\s+'             # CUSIP (9 chars)
            r'([\d,]+\.?\d*)\s+'            # Shares
            r'\$?([\d,]+\.?\d*)\s+'         # Price
            r'\$?([\d,]+\.?\d*)$'           # Value
        )

        # Pattern for lines where symbol/CUSIP might be embedded or missing
        # e.g.: BROWN FORMAN CORP CL B BF.B 0.07888 $26.0600 $2.06
        flexible_pattern = re.compile(
            r'^([A-Z][A-Za-z0-9\s&\'\-\.\(\),]+?)\s+'  # Security name
            r'([A-Z][A-Z0-9\.]{0,5})\s+'               # Symbol
            r'([\d,]+\.?\d*)\s+'                        # Shares
            r'\$?([\d,]+\.?\d*)\s+'                     # Price
            r'\$?([\d,]+\.?\d*)$'                       # Value
        )

        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Track category headers - these are lines without numbers that label sections
            # Only treat as header if it doesn't contain price/value patterns (e.g., $xxx.xx)
            is_header_line = not re.search(r'\$[\d,]+\.?\d*', line)

            if is_header_line:
                if "ETF" in line.upper() or "STOCK" in line.upper():
                    if "MONEY MARKET" not in line.upper():
                        current_category = "ETF"
                        continue
                if line.upper() == "MONEY MARKET FUNDS" or line.upper().startswith("MONEY MARKET"):
                    current_category = "MONEY_MARKET"
                    continue
                if line.upper() == "OTHER":
                    current_category = "OTHER"
                    continue
                if line.upper() == "CASH":
                    current_category = "CASH"
                    continue

            # Skip header lines and non-holdings lines
            skip_patterns = [
                r'^security\s+symbol',  # Table header
                r'^total\s+\$',         # Total lines
                r'^page\s+\d+',         # Page numbers
                r'^\d{1,2}/\d{1,2}/\d{4}',  # Date lines (transaction dates)
                r'^starting\s+balance', # Starting balance
                r'^ending\s+balance',   # Ending balance
                r'^december\s+\d',      # Date header
                r'wealthfront\s*:',     # Account number line
                r'^currency\s+value',   # Cash section header
                r'^us\s+dollar',        # Cash currency line
                r'^holdings\s+as\s+of', # Holdings header
                r'^i\.\s+holdings',     # Section header
                r'^ge\s+gao',           # Name header
                r'^joint\s+s&p',        # Portfolio name
            ]

            if any(re.search(pat, line.lower()) for pat in skip_patterns):
                continue

            # Try to match holdings pattern
            match = holdings_pattern.match(line)
            if not match:
                match = cusip_pattern.match(line)
            if not match:
                match = flexible_pattern.match(line)

            if match:
                security_name = match.group(1).strip()
                symbol_or_cusip = match.group(2).strip()

                # Skip if security name looks like a date or transaction
                if re.match(r'^\d{1,2}/\d{1,2}/\d{4}', security_name):
                    continue

                # Determine if it's a symbol or CUSIP
                symbol = None
                cusip = None
                if len(symbol_or_cusip) == 9 and symbol_or_cusip.isalnum():
                    cusip = symbol_or_cusip
                else:
                    symbol = symbol_or_cusip

                try:
                    quantity = Decimal(match.group(3).replace(",", ""))
                    price = Decimal(match.group(4).replace(",", ""))
                    market_value = Decimal(match.group(5).replace(",", ""))

                    # Skip unreasonable values (likely parsing errors)
                    if market_value > Decimal("10000000"):  # $10M threshold
                        continue
                    if quantity > Decimal("1000000"):  # 1M shares threshold
                        continue

                    if market_value > 0:
                        security_type = self._classify_security_type(security_name, symbol, current_category)
                        asset_class = self._classify_asset_class(security_type, security_name)

                        positions.append(PositionData(
                            symbol=symbol,
                            cusip=cusip,
                            security_name=security_name,
                            security_type=security_type,
                            quantity=quantity,
                            price=price,
                            market_value=market_value,
                            cost_basis=None,
                            asset_class=asset_class,
                            row_index=row_index,
                        ))
                        row_index += 1
                except (InvalidOperation, IndexError):
                    pass

        return positions

    def _classify_security_type(self, name: str, symbol: Optional[str], category: str = "ETF") -> str:
        """Classify security type based on name, symbol, and category."""
        name_lower = name.lower()

        # Use category from parsing context
        if category == "MONEY_MARKET":
            return "MONEY_MARKET"
        if category == "CASH":
            return "CASH"

        # Money market funds by symbol
        if symbol and symbol in ["TIMXX", "SWVXX", "SPAXX", "FDRXX"]:
            return "MONEY_MARKET"

        # Money market by name
        if "money market" in name_lower:
            return "MONEY_MARKET"

        # Cash
        if name_lower == "cash":
            return "CASH"

        # ETFs
        if "etf" in name_lower or "exchange traded" in name_lower:
            return "ETF"
        if "index" in name_lower or "fund" in name_lower:
            return "ETF"

        # Common Wealthfront ETF symbols
        wealthfront_etfs = ["VTI", "VEA", "VWO", "VIG", "VTIP", "SCHF", "IEMG",
                           "MUB", "LQD", "BNDX", "VNQ", "GLD", "XLE", "VOO"]
        if symbol and symbol in wealthfront_etfs:
            return "ETF"

        # Default to stock (most individual holdings are stocks)
        return "STOCK"

    def _classify_asset_class(self, security_type: str, name: str) -> str:
        """Classify asset class based on security type and name."""
        name_lower = name.lower()

        if security_type in ["CASH", "MONEY_MARKET"]:
            return "CASH"
        if "bond" in name_lower or "treasury" in name_lower or "fixed income" in name_lower:
            return "FIXED_INCOME"
        if "tip" in name_lower or "inflation" in name_lower:
            return "FIXED_INCOME"
        if "muni" in name_lower or "municipal" in name_lower:
            return "FIXED_INCOME"
        if "gold" in name_lower or "silver" in name_lower or "commodity" in name_lower:
            return "ALTERNATIVE"
        if "real estate" in name_lower or "reit" in name_lower:
            return "ALTERNATIVE"
        if security_type in ["STOCK", "ETF", "MUTUAL_FUND"]:
            return "EQUITY"

        return "UNKNOWN"
