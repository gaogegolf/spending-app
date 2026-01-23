"""Vanguard brokerage/401(k) statement parser."""

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


class VanguardBrokerageParser(BaseBrokerageParser):
    """Parser for Vanguard brokerage and 401(k) statements.

    Handles quarterly statements with Investment Activity tables.
    """

    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.provider = "vanguard"

    def parse(self) -> BrokerageParseResult:
        """Parse Vanguard statement and return holdings snapshot."""
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
            errors.append(f"Failed to parse Vanguard statement: {str(e)}")
            return BrokerageParseResult(
                success=False,
                provider=self.provider,
                account_type=self.account_type or "RETIREMENT_401K",
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

    def _extract_account_identifier(self) -> str:
        """Extract account identifier from Vanguard statement.

        Looks for patterns like:
        - "SAP AMERICA, INC. 401(K) PLAN–– 090061"
        - Account number at end of plan name line
        """
        # Pattern for 401(k) plan with account number
        # Format: COMPANY NAME 401(K) PLAN–– XXXXXX
        pattern = r"401\(K\)\s*PLAN[–\-]+\s*(\d{6})"
        match = re.search(pattern, self.full_text, re.IGNORECASE)

        if match:
            account_num = match.group(1)
            return f"****{account_num[-4:]}"

        # Try alternative pattern for IRA or other accounts
        pattern2 = r"Account(?:\s+Number)?[:\s]+(\d{6,})"
        match = re.search(pattern2, self.full_text, re.IGNORECASE)

        if match:
            account_num = match.group(1)
            return f"****{account_num[-4:]}"

        return "Unknown"

    def _extract_statement_dates(self) -> Tuple[Optional[date], Optional[date]]:
        """Extract statement date range from Vanguard statement.

        Looks for patterns like:
        - "ACCOUNT SUMMARY: 10/01/2025 - 12/31/2025"
        - "MM/DD/YYYY - MM/DD/YYYY"
        """
        # Try MM/DD/YYYY - MM/DD/YYYY format
        date_range_pattern = r"(\d{1,2}/\d{1,2}/\d{4})\s*[-–]\s*(\d{1,2}/\d{1,2}/\d{4})"
        match = re.search(date_range_pattern, self.full_text)

        if match:
            start_str = match.group(1)
            end_str = match.group(2)
            try:
                start_date = datetime.strptime(start_str, "%m/%d/%Y").date()
                end_date = datetime.strptime(end_str, "%m/%d/%Y").date()
                return end_date, start_date
            except ValueError:
                pass

        # Try "as of MM/DD/YYYY" format
        as_of_pattern = r"as\s+of\s+(\d{1,2}/\d{1,2}/\d{4})"
        match = re.search(as_of_pattern, self.full_text, re.IGNORECASE)

        if match:
            try:
                end_date = datetime.strptime(match.group(1), "%m/%d/%Y").date()
                return end_date, None
            except ValueError:
                pass

        return None, None

    def _extract_totals(self) -> Tuple[Decimal, Decimal, Decimal]:
        """Extract total values from Vanguard statement.

        Looks for:
        - "Total Account Balance: $XXX,XXX.XX"
        - "Ending balance $XXX,XXX.XX"
        - "Total Invested $XXX,XXX.XX"
        """
        total_value = Decimal("0")
        total_cash = Decimal("0")
        total_securities = Decimal("0")

        # Extract total account balance
        value_patterns = [
            r"Total\s+Account\s+Balance[:\s]*\$?([\d,]+\.?\d*)",
            r"Ending\s+balance[:\s]*\$?([\d,]+\.?\d*)",
            r"Total\s+Invested[:\s]*\$?([\d,]+\.?\d*)",
        ]

        for pattern in value_patterns:
            match = re.search(pattern, self.full_text, re.IGNORECASE)
            if match:
                try:
                    total_value = Decimal(match.group(1).replace(",", ""))
                    break
                except InvalidOperation:
                    continue

        # For Vanguard 401(k), most is securities, cash is usually minimal
        # Look for money market or short-term reserves
        cash_patterns = [
            r"Short-Term\s+Reserves[:\s]*\$?([\d,]+\.?\d*)",
            r"Money\s+Market[:\s]*\$?([\d,]+\.?\d*)",
        ]

        for pattern in cash_patterns:
            match = re.search(pattern, self.full_text, re.IGNORECASE)
            if match:
                try:
                    total_cash = Decimal(match.group(1).replace(",", ""))
                    break
                except InvalidOperation:
                    continue

        total_securities = total_value - total_cash

        return total_value, total_cash, total_securities

    def _extract_positions(self) -> List[PositionData]:
        """Extract position/holdings data from Vanguard statement.

        Vanguard statements have an Investment Activity table with columns:
        - Fund Name
        - Beginning Balance
        - Contributions
        - Other Transactions
        - Market Gain/Loss
        - Dividends/Capital Gains
        - Ending Balance
        """
        positions = []
        row_index = 0

        # Try table extraction first
        for page in self.pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue

                # Check if this looks like an Investment Activity table
                header_row = table[0] if table else []
                if self._is_investment_activity_table(header_row):
                    # Parse investment rows
                    for row in table[1:]:
                        position = self._parse_investment_row(row, row_index)
                        if position:
                            positions.append(position)
                            row_index += 1

        # If no tables found, try text extraction
        if not positions:
            positions = self._extract_positions_from_text()

        return positions

    def _is_investment_activity_table(self, header_row: List) -> bool:
        """Check if this table header looks like an Investment Activity table."""
        if not header_row:
            return False

        header_text = " ".join(str(cell or "").lower() for cell in header_row)
        indicators = ["balance", "contributions", "gain", "loss", "ending"]
        return sum(1 for ind in indicators if ind in header_text) >= 2

    def _parse_investment_row(self, row: List, row_index: int) -> Optional[PositionData]:
        """Parse a single investment table row into PositionData."""
        if not row or len(row) < 2:
            return None

        # Skip total/summary rows
        first_cell = str(row[0] or "").lower()
        if any(skip in first_cell for skip in ["total", "---", "page"]):
            return None

        try:
            # First cell is fund name
            security_name = str(row[0] or "").strip()
            if not security_name or len(security_name) < 3:
                return None

            # Last cell is typically Ending Balance
            market_value = None
            for cell in reversed(row[1:]):
                cell_str = str(cell or "").strip()
                if cell_str and cell_str not in ["-", "--", "$0.00"]:
                    value = self._parse_currency(cell_str)
                    if value is not None and value > 0:
                        market_value = value
                        break

            if market_value is None or market_value == 0:
                return None

            # Determine security type and asset class
            security_type = self._classify_security_type(security_name)
            asset_class = self._classify_asset_class(security_type, security_name)

            return PositionData(
                symbol=None,  # Vanguard funds don't always show symbols
                cusip=None,
                security_name=security_name,
                security_type=security_type,
                quantity=None,  # Not provided in 401(k) statements
                price=None,
                market_value=market_value,
                cost_basis=None,
                asset_class=asset_class,
                row_index=row_index,
            )

        except Exception:
            return None

    def _extract_positions_from_text(self) -> List[PositionData]:
        """Extract positions from text when table extraction fails.

        Vanguard Investment Activity format:
        Vanguard® Target Retire $332,405.25 $2,637.18 - $4.34 $10,155.07 $0.00 $345,193.16
        2050 Tr P
        """
        positions = []
        row_index = 0
        lines = self.full_text.split('\n')

        # Look for Investment Activity section
        in_activity_section = False
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Detect start of Investment Activity section
            if "Investment Activity" in line:
                in_activity_section = True
                i += 1
                continue

            # Detect end of section
            if in_activity_section and any(x in line for x in ["Fee Summary", "Recommendations", "Additional"]):
                break

            if in_activity_section:
                # Pattern: Fund Name followed by multiple dollar amounts
                # The last amount is the Ending Balance
                # Look for lines with Vanguard fund names or other fund patterns
                if self._looks_like_fund_line(line):
                    # Try to extract fund name and ending balance
                    position = self._parse_fund_line(line, lines, i, row_index)
                    if position:
                        positions.append(position)
                        row_index += 1

            i += 1

        return positions

    def _looks_like_fund_line(self, line: str) -> bool:
        """Check if line looks like a fund entry."""
        # Vanguard funds often start with "Vanguard" or contain fund-like words
        fund_indicators = ["vanguard", "target", "retire", "trust", "fund", "index"]
        line_lower = line.lower()
        return any(ind in line_lower for ind in fund_indicators) and "$" in line

    def _parse_fund_line(
        self,
        line: str,
        lines: List[str],
        line_index: int,
        row_index: int
    ) -> Optional[PositionData]:
        """Parse a fund line and extract position data."""
        try:
            # Extract all dollar amounts from the line
            amounts = re.findall(r'\$?([\d,]+\.?\d{0,2})', line)
            if len(amounts) < 2:
                return None

            # Last amount is ending balance
            market_value = Decimal(amounts[-1].replace(",", ""))
            if market_value <= 0:
                return None

            # Extract fund name (everything before the first dollar amount)
            dollar_pos = line.find("$")
            if dollar_pos == -1:
                # No dollar sign, try to find first number
                match = re.search(r'[\d,]+\.?\d{0,2}', line)
                if match:
                    dollar_pos = match.start()
                else:
                    return None

            security_name = line[:dollar_pos].strip()

            # Check next line for continuation of fund name
            if line_index + 1 < len(lines):
                next_line = lines[line_index + 1].strip()
                # If next line doesn't have dollar amounts, it might be part of name
                if next_line and "$" not in next_line and not next_line[0].isdigit():
                    if len(next_line) < 30:  # Reasonable continuation
                        security_name = security_name + " " + next_line

            # Clean up fund name
            security_name = re.sub(r'[®™]', '', security_name).strip()

            if len(security_name) < 3:
                return None

            security_type = self._classify_security_type(security_name)
            asset_class = self._classify_asset_class(security_type, security_name)

            return PositionData(
                symbol=None,
                cusip=None,
                security_name=security_name,
                security_type=security_type,
                quantity=None,
                price=None,
                market_value=market_value,
                cost_basis=None,
                asset_class=asset_class,
                row_index=row_index,
            )

        except (InvalidOperation, IndexError):
            return None

    def _parse_currency(self, value_str: str) -> Optional[Decimal]:
        """Parse a currency string to Decimal."""
        if not value_str:
            return None

        # Remove currency symbols and clean up
        cleaned = value_str.replace("$", "").replace(",", "").strip()
        if cleaned in ["-", "--", "", "N/A", "n/a"]:
            return None

        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    def _classify_security_type(self, name: str) -> str:
        """Classify security type based on name."""
        name_lower = name.lower()

        if "money market" in name_lower or "cash" in name_lower:
            return "MONEY_MARKET"
        if "target" in name_lower and "retire" in name_lower:
            return "MUTUAL_FUND"  # Target date funds
        if "trust" in name_lower:
            return "MUTUAL_FUND"  # Stable value/trust funds
        if "index" in name_lower or "idx" in name_lower:
            return "MUTUAL_FUND"
        if "etf" in name_lower:
            return "ETF"
        if "bond" in name_lower or "fixed" in name_lower:
            return "BOND"

        return "MUTUAL_FUND"  # Default for 401(k) funds

    def _classify_asset_class(self, security_type: str, name: str) -> str:
        """Classify asset class based on security type and name."""
        name_lower = name.lower()

        if security_type == "MONEY_MARKET":
            return "CASH"
        if "bond" in name_lower or "fixed" in name_lower or "income" in name_lower:
            return "FIXED_INCOME"
        if "stable" in name_lower or "trust" in name_lower:
            # Stable value funds are typically fixed income
            return "FIXED_INCOME"
        if "target" in name_lower and "retire" in name_lower:
            # Target date funds are primarily equity
            return "EQUITY"
        if "stock" in name_lower or "equity" in name_lower or "index" in name_lower:
            return "EQUITY"

        return "EQUITY"  # Default for 401(k) is equity
