"""Schwab brokerage statement parser."""

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


class SchwabBrokerageParser(BaseBrokerageParser):
    """Parser for Charles Schwab brokerage statements."""

    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.provider = "schwab"

    def parse(self) -> BrokerageParseResult:
        """Parse Schwab statement and return holdings snapshot."""
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
                account_number_raw=self._raw_account_number,
                raw_metadata={
                    "pages": len(self.pdf.pages) if self.pdf else 0,
                    "position_count": len(positions),
                },
            )

        except Exception as e:
            errors.append(f"Failed to parse Schwab statement: {str(e)}")
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

    def _extract_account_identifier(self) -> str:
        """Extract masked account identifier from Schwab statement.

        Schwab account numbers are typically in format:
        - ####-#### (e.g., 6404-9694)
        """
        # Look for Account Number pattern
        pattern = r"Account\s*Number[:\s]*(\d{4}-\d{4})"
        match = re.search(pattern, self.full_text, re.IGNORECASE)

        if match:
            account_num = match.group(1)
            self._raw_account_number = account_num
            # Mask the account number, showing only last 4 digits
            return f"****{account_num[-4:]}"

        return "Unknown"

    def _extract_statement_dates(self) -> Tuple[Optional[date], Optional[date]]:
        """Extract statement date range from Schwab statement.

        Looks for patterns like:
        - "Statement Period December 1-31, 2025"
        - "December1-31,2025" (no spaces - common in PDF extraction)
        """
        # Try "Month Day-Day, Year" format (Schwab style) - with optional spaces
        # Pattern handles both "December 1-31, 2025" and "December1-31,2025"
        date_pattern = r"(January|February|March|April|May|June|July|August|September|October|November|December)\s*(\d{1,2})-(\d{1,2}),?\s*(\d{4})"
        match = re.search(date_pattern, self.full_text, re.IGNORECASE)

        if match:
            month = match.group(1)
            start_day = match.group(2)
            end_day = match.group(3)
            year = match.group(4)
            try:
                start_date = datetime.strptime(f"{month} {start_day}, {year}", "%B %d, %Y").date()
                end_date = datetime.strptime(f"{month} {end_day}, {year}", "%B %d, %Y").date()
                return end_date, start_date
            except ValueError:
                pass

        # Try "as of MM/DD/YYYY" or "asof12/31" pattern (handles no spaces)
        as_of_pattern = r"as\s*of\s*(\d{1,2}/\d{1,2})(?:/(\d{4}))?"
        match = re.search(as_of_pattern, self.full_text, re.IGNORECASE)

        if match:
            date_str = match.group(1)
            # If year is in the pattern, use it
            if match.group(2):
                year = match.group(2)
            else:
                # Find the year from nearby context - look for 4-digit year in statement
                year_match = re.search(r"(?:Period|Statement).*?(20\d{2})", self.full_text, re.IGNORECASE)
                if year_match:
                    year = year_match.group(1)
                else:
                    # Fallback: find any 20XX year
                    year_match = re.search(r"20\d{2}", self.full_text)
                    year = year_match.group(0) if year_match else str(datetime.now().year)
            try:
                end_date = datetime.strptime(f"{date_str}/{year}", "%m/%d/%Y").date()
                return end_date, None
            except ValueError:
                pass

        return None, None

    def _extract_totals(self) -> Tuple[Decimal, Decimal, Decimal]:
        """Extract total values from Schwab statement.

        Looks for:
        - Ending Account Value
        - Cash and Cash Investments total
        - Equities total
        """
        total_value = Decimal("0")
        total_cash = Decimal("0")
        total_securities = Decimal("0")

        # Extract total account value
        # Pattern: "Ending Account Value as of 12/31 $215,073.31"
        value_patterns = [
            r"Ending\s+Account\s+Value[^$]*\$([\d,]+\.?\d*)",
            r"Account\s+Value[:\s]*\$([\d,]+\.?\d*)",
            r"Total[:\s]*\$([\d,]+\.?\d*)\s+100%",
        ]

        for pattern in value_patterns:
            match = re.search(pattern, self.full_text, re.IGNORECASE)
            if match:
                try:
                    total_value = Decimal(match.group(1).replace(",", ""))
                    break
                except InvalidOperation:
                    continue

        # Extract Cash total from Asset Allocation
        # Pattern: "Cash and Cash Investments 544.06 <1%"
        cash_pattern = r"Cash\s+and\s+Cash\s+Investments[:\s]*([\d,]+\.?\d*)"
        match = re.search(cash_pattern, self.full_text, re.IGNORECASE)
        if match:
            try:
                total_cash = Decimal(match.group(1).replace(",", ""))
            except InvalidOperation:
                pass

        # Alternative: Total Cash and Cash Investments
        if total_cash == 0:
            cash_pattern2 = r"Total\s+Cash\s+and\s+Cash\s+Investments[^$]*\$([\d,]+\.?\d*)[^$]*\$([\d,]+\.?\d*)"
            match = re.search(cash_pattern2, self.full_text, re.IGNORECASE)
            if match:
                try:
                    total_cash = Decimal(match.group(2).replace(",", ""))
                except InvalidOperation:
                    pass

        # Extract Equities total
        # Pattern: "Equities 214,529.25 100%"
        securities_pattern = r"(?:Equities|Total\s+Equities)[:\s]*([\d,]+\.?\d*)"
        match = re.search(securities_pattern, self.full_text, re.IGNORECASE)
        if match:
            try:
                total_securities = Decimal(match.group(1).replace(",", ""))
            except InvalidOperation:
                pass

        # Alternative: from Positions - Equities total
        if total_securities == 0:
            securities_pattern2 = r"Total\s+Equities[^$]*\$([\d,]+\.?\d*)"
            match = re.search(securities_pattern2, self.full_text, re.IGNORECASE)
            if match:
                try:
                    total_securities = Decimal(match.group(1).replace(",", ""))
                except InvalidOperation:
                    pass

        return total_value, total_cash, total_securities

    def _extract_positions(self) -> List[PositionData]:
        """Extract position/holdings data from Schwab statement.

        Schwab statements have:
        - Positions - Equities section with Symbol, Description, Quantity, Price, Market Value
        - Cash and Cash Investments section with Bank Sweep balances
        """
        positions = []
        row_index = 0

        # Extract from tables
        for page in self.pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue

                # Check for equities table
                header_text = " ".join(str(cell or "").lower() for cell in (table[0] if table else []))

                if "symbol" in header_text or "description" in header_text:
                    for row in table[1:]:
                        position = self._parse_position_row(row, row_index)
                        if position:
                            positions.append(position)
                            row_index += 1

        # If no positions found from tables, try text extraction
        if not positions:
            positions = self._extract_positions_from_text()

        # Add cash position if we have a cash balance
        cash_position = self._extract_cash_position(row_index)
        if cash_position:
            positions.append(cash_position)

        return positions

    def _parse_position_row(self, row: List, row_index: int) -> Optional[PositionData]:
        """Parse a single position row into PositionData."""
        if not row or len(row) < 4:
            return None

        # Skip header/summary rows
        first_cell = str(row[0] or "").lower()
        if any(skip in first_cell for skip in ["total", "symbol", "type", "---", "bank sweep"]):
            return None

        try:
            # Schwab format: Symbol, Description, Quantity, Price($), Market Value($), Cost Basis($), etc.
            symbol = str(row[0] or "").strip().upper()
            if not symbol or len(symbol) > 10:
                return None

            description = str(row[1] or "").strip() if len(row) > 1 else ""
            if not description:
                return None

            # Find numeric columns
            quantity = None
            price = None
            market_value = None
            cost_basis = None

            for i, cell in enumerate(row[2:], 2):
                cell_str = str(cell or "").strip()
                value = self._parse_currency(cell_str)
                if value is None:
                    continue

                # Heuristics based on typical Schwab column order
                if i == 2 and value < 100000:  # Quantity
                    quantity = value
                elif i == 3 and value < 10000:  # Price
                    price = value
                elif i == 4:  # Market Value
                    market_value = value
                elif i == 5:  # Cost Basis
                    cost_basis = value

            if market_value is None or market_value == 0:
                return None

            security_type = self._classify_security_type(description, symbol)
            asset_class = self._classify_asset_class(security_type, description)

            return PositionData(
                symbol=symbol if symbol else None,
                cusip=None,
                security_name=description,
                security_type=security_type,
                quantity=quantity,
                price=price,
                market_value=market_value,
                cost_basis=cost_basis,
                asset_class=asset_class,
                row_index=row_index,
            )

        except Exception:
            return None

    def _extract_positions_from_text(self) -> List[PositionData]:
        """Extract positions from text when table extraction fails."""
        positions = []
        row_index = 0

        # Pattern for equities: "META META PLATFORMS INC 325.0000 660.09000 214,529.25 198,149.87 16,379.38"
        pattern = r"([A-Z]{1,5})\s+([A-Z][A-Z\s]+(?:INC|CORP|LLC|LTD|CO)?)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)"

        for match in re.finditer(pattern, self.full_text):
            try:
                symbol = match.group(1).strip()
                description = match.group(2).strip()
                quantity = Decimal(match.group(3).replace(",", ""))
                price = Decimal(match.group(4).replace(",", ""))
                market_value = Decimal(match.group(5).replace(",", ""))

                if market_value > 0:
                    security_type = self._classify_security_type(description, symbol)
                    asset_class = self._classify_asset_class(security_type, description)

                    positions.append(PositionData(
                        symbol=symbol,
                        cusip=None,
                        security_name=description,
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
                continue

        return positions

    def _extract_cash_position(self, row_index: int) -> Optional[PositionData]:
        """Extract cash/bank sweep position."""
        # Look for Bank Sweep balance
        # Pattern: "Total Cash and Cash Investments $373.42 $544.06"
        pattern = r"Total\s+Cash\s+and\s+Cash\s+Investments[^$]*\$[\d,]+\.?\d*[^$]*\$([\d,]+\.?\d*)"
        match = re.search(pattern, self.full_text, re.IGNORECASE)

        if match:
            try:
                cash_value = Decimal(match.group(1).replace(",", ""))
                if cash_value > 0:
                    return PositionData(
                        symbol=None,
                        cusip=None,
                        security_name="CHARLES SCHWAB BANK SWEEP",
                        security_type="CASH",
                        quantity=cash_value,
                        price=Decimal("1.00"),
                        market_value=cash_value,
                        cost_basis=None,
                        asset_class="CASH",
                        row_index=row_index,
                    )
            except InvalidOperation:
                pass

        # Alternative: look for Ending Balance in Bank Sweep Activity
        pattern2 = r"Ending\s+Balance[^$]*\$([\d,]+\.?\d*)"
        match = re.search(pattern2, self.full_text, re.IGNORECASE)
        if match:
            try:
                cash_value = Decimal(match.group(1).replace(",", ""))
                if cash_value > 0:
                    return PositionData(
                        symbol=None,
                        cusip=None,
                        security_name="CHARLES SCHWAB BANK SWEEP",
                        security_type="CASH",
                        quantity=cash_value,
                        price=Decimal("1.00"),
                        market_value=cash_value,
                        cost_basis=None,
                        asset_class="CASH",
                        row_index=row_index,
                    )
            except InvalidOperation:
                pass

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

    def _classify_security_type(self, name: str, symbol: Optional[str]) -> str:
        """Classify security type based on name and symbol."""
        name_lower = name.lower()

        if "bank" in name_lower or "sweep" in name_lower or "cash" in name_lower:
            return "CASH"
        if "money market" in name_lower:
            return "MONEY_MARKET"
        if "etf" in name_lower or "exchange traded" in name_lower:
            return "ETF"
        if "fund" in name_lower:
            return "MUTUAL_FUND"
        if "bond" in name_lower or "treasury" in name_lower:
            return "BOND"

        # Default to stock for individual equities
        return "STOCK"

    def _classify_asset_class(self, security_type: str, name: str) -> str:
        """Classify asset class based on security type and name."""
        if security_type in ["CASH", "MONEY_MARKET"]:
            return "CASH"
        if security_type == "BOND" or "bond" in name.lower() or "treasury" in name.lower():
            return "FIXED_INCOME"
        if security_type in ["STOCK", "ETF", "MUTUAL_FUND"]:
            return "EQUITY"

        return "UNKNOWN"
