"""Equatex/EquatePlus employee stock plan statement parser."""

import re
from typing import List, Optional, Tuple
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.services.file_parser.brokerage_parser import (
    BaseBrokerageParser,
    BrokerageParseResult,
    PositionData,
)


class EquatexBrokerageParser(BaseBrokerageParser):
    """Parser for EquatePlus/Equatex employee stock plan statements.

    Supports SAP and other company stock plan statements that track:
    - ESPP (Employee Stock Purchase Plan) shares
    - RSUs (Restricted Stock Units) - vested and unvested
    - Company stock from various plans (e.g., "Own SAP", "Move SAP", "Grow SAP")

    Only extracts vested/available positions for net worth calculation.
    Locked/unvested RSUs are excluded from totals.
    """

    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.provider = "equatex"
        self.account_type = "STOCK_PLAN"
        self._share_price_eur: Optional[Decimal] = None
        self._share_price_usd: Optional[Decimal] = None

    def parse(self) -> BrokerageParseResult:
        """Parse Equatex statement and return holdings snapshot."""
        errors = []
        warnings = []

        try:
            self._open_pdf()

            # Equatex is always a stock plan account
            self.account_type = "STOCK_PLAN"

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
                    f"reported Available total ${total_value} by ${reconciliation_diff}"
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
                    "share_price_eur": str(self._share_price_eur) if self._share_price_eur else None,
                },
            )

        except Exception as e:
            errors.append(f"Failed to parse Equatex statement: {str(e)}")
            return BrokerageParseResult(
                success=False,
                provider=self.provider,
                account_type=self.account_type or "STOCK_PLAN",
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
        """Extract User ID from Equatex statement header.

        Pattern: "User ID: 6983577"
        """
        # Look for "User ID: XXXXXXX" pattern
        user_id_pattern = r"User\s+ID[:\s]+(\d+)"
        match = re.search(user_id_pattern, self.full_text, re.IGNORECASE)

        if match:
            user_id = match.group(1)
            self._raw_account_number = user_id
            # Mask all but last 4 digits
            return f"****{user_id[-4:]}"

        return "Unknown"

    def _extract_statement_dates(self) -> Tuple[Optional[date], Optional[date]]:
        """Extract statement date(s) from Equatex statement.

        Looks for:
        - "as of 31 Dec 2025" - statement end date
        - "1 Jan 2025 - 31 Dec 2025" - period range
        """
        statement_date = None
        statement_start_date = None

        # Pattern: "as of DD Mon YYYY"
        as_of_pattern = r"as\s+of\s+(\d{1,2})\s+(\w+)\s+(\d{4})"
        match = re.search(as_of_pattern, self.full_text, re.IGNORECASE)

        if match:
            try:
                day = int(match.group(1))
                month_str = match.group(2)
                year = int(match.group(3))
                month_date = datetime.strptime(month_str, "%b")
                statement_date = date(year, month_date.month, day)
            except ValueError:
                pass

        # Pattern: "DD Mon YYYY - DD Mon YYYY" (period range)
        period_pattern = r"(\d{1,2})\s+(\w{3})\s+(\d{4})\s*[-–]\s*(\d{1,2})\s+(\w{3})\s+(\d{4})"
        match = re.search(period_pattern, self.full_text)

        if match:
            try:
                start_day = int(match.group(1))
                start_month_str = match.group(2)
                start_year = int(match.group(3))
                start_month_date = datetime.strptime(start_month_str, "%b")
                statement_start_date = date(start_year, start_month_date.month, start_day)

                # Also extract end date from period if we didn't get it from "as of"
                if not statement_date:
                    end_day = int(match.group(4))
                    end_month_str = match.group(5)
                    end_year = int(match.group(6))
                    end_month_date = datetime.strptime(end_month_str, "%b")
                    statement_date = date(end_year, end_month_date.month, end_day)
            except ValueError:
                pass

        return statement_date, statement_start_date

    def _extract_totals(self) -> Tuple[Decimal, Decimal, Decimal]:
        """Extract total values from Equatex statement.

        IMPORTANT: Uses "Available" value (vested only), NOT full portfolio value.
        Locked/unvested RSUs are excluded from net worth.

        Looks for:
        - "Available" followed by USD value
        - "Your portfolio" total (for reference, not used)
        """
        total_value = Decimal("0")
        total_cash = Decimal("0")  # Stock plans typically have no cash
        total_securities = Decimal("0")

        # Pattern for Available amount (vested shares only)
        # Format: "Available\nLocked\n33 093.99 USD" or similar
        # The value may use space as thousand separator (European format)
        available_patterns = [
            # "Available" followed eventually by a USD amount
            r"Available\s*\n?\s*(?:Locked\s*\n?\s*)?([\d\s]+\.?\d*)\s*USD",
            # Alternative: "33 093.99 USD" after Available/Locked headers
            r"Available.*?Locked.*?([\d\s]+\.\d{2})\s*USD",
        ]

        for pattern in available_patterns:
            match = re.search(pattern, self.full_text, re.IGNORECASE | re.DOTALL)
            if match:
                try:
                    # Remove spaces from number (European format uses space as thousands separator)
                    value_str = match.group(1).replace(" ", "").strip()
                    total_value = Decimal(value_str)
                    break
                except InvalidOperation:
                    continue

        # If no Available found, try alternative extraction from page 1
        if total_value == 0:
            # Look for the portfolio section structure
            # "95 063.24 USD" followed by "Available" / "Locked" / "33 093.99 USD" / "61 969.25 USD"
            portfolio_pattern = r"([\d\s]+\.\d{2})\s*USD\s*\n?\s*Available\s*\n?\s*Locked\s*\n?\s*([\d\s]+\.\d{2})\s*USD"
            match = re.search(portfolio_pattern, self.full_text, re.IGNORECASE)
            if match:
                try:
                    # Second group is the Available value
                    value_str = match.group(2).replace(" ", "").strip()
                    total_value = Decimal(value_str)
                except InvalidOperation:
                    pass

        total_securities = total_value  # All value is in securities for stock plans

        return total_value, total_cash, total_securities

    def _extract_positions(self) -> List[PositionData]:
        """Extract position/holdings data from Equatex statement.

        Extracts only vested/available shares from each plan:
        - Own SAP: ESPP shares (typically all vested)
        - Move SAP: RSU shares that have vested + any purchased shares
        - Grow SAP: May have some vested shares

        Locked RSUs are NOT included in positions for net worth calculation.
        """
        positions = []
        row_index = 0

        # First, extract the share price (used for all SAP positions)
        self._extract_share_price()

        # Look for "Available" lines in plan sections
        # Pattern: "Available XX.XXXX YY YYY.YY EUR" where XX.XXXX is shares and YY YYY.YY is EUR value
        # Each plan section has this format after a "Plan Name XX YYY.YY USD" header

        # Find all plan sections with Available shares
        # Own SAP pattern: "Own SAP ... Available 41.42732 10 133.70 EUR"
        # Move SAP pattern: "Move SAP ... Available 93.8634 22 960.29 EUR"
        plan_patterns = [
            ("Own SAP", "ESPP"),
            ("Move SAP", "STOCK"),
            ("Grow SAP", "STOCK"),
        ]

        for plan_name, security_type in plan_patterns:
            position = self._extract_available_position(plan_name, security_type, row_index)
            if position:
                positions.append(position)
                row_index += 1

        return positions

    def _extract_share_price(self) -> None:
        """Extract SAP share price from statement.

        Pattern: "SAP: 208.35 EUR as of 30 Dec 2025 (XETRA)"
        """
        price_pattern = r"SAP[:\s]+([\d,\.]+)\s*EUR\s*as\s*of"
        match = re.search(price_pattern, self.full_text)

        if match:
            try:
                # Handle both comma and dot as decimal separator
                price_str = match.group(1).replace(",", ".")
                self._share_price_eur = Decimal(price_str)
            except InvalidOperation:
                pass

    def _extract_available_position(
        self, plan_name: str, security_type: str, row_index: int
    ) -> Optional[PositionData]:
        """Extract available (vested) position for a specific plan.

        Looks for the detailed plan section (not page 1 summary) which has:
        - "Plan Name XX YYY.YY USD" followed by "Shares Total" and "Available X Y.YY EUR"

        Args:
            plan_name: Name of the plan (e.g., "Own SAP")
            security_type: Security type to assign (ESPP, STOCK, etc.)
            row_index: Position index

        Returns:
            PositionData for vested shares, or None if no vested shares
        """
        # Find plan sections by looking for "Plan Name XX YYY.YY USD" pattern
        plan_pattern = rf"{re.escape(plan_name)}\s+([\d\s]+\.\d{{2}})\s*USD"

        plan_matches = list(re.finditer(plan_pattern, self.full_text))
        if not plan_matches:
            return None

        # For each plan match, check if it's a detail section (has "Shares Total" nearby)
        # Page 1 summary doesn't have this pattern
        for plan_match in plan_matches:
            start_pos = plan_match.end()
            search_text = self.full_text[start_pos:start_pos + 600]

            # Check if this is a detail section by looking for "Shares Total" or "Locked" directly
            # Page 1 summary sections go to the next plan without these patterns
            is_detail_section = (
                "Shares Total" in search_text[:200] or
                re.search(r"Locked\s+\d+\s+[\d\s]+\.\d{2}\s*USD", search_text[:200])
            )

            if not is_detail_section:
                # This is likely the page 1 summary, skip it
                continue

            # Look for "Available SHARES VALUE EUR" pattern
            available_pattern = r"Available\s+([\d\.]+)\s+([\d\s]+\.\d{2})\s*EUR"
            available_match = re.search(available_pattern, search_text)

            if available_match:
                try:
                    shares = Decimal(available_match.group(1).strip())

                    # Check if shares > 0 (has vested shares)
                    if shares <= 0:
                        continue

                    # Find the USD value for vested shares
                    # Look for pattern "SHARES USD_VALUE USD" just before Available
                    # Example: "93.8634 22 960.29 USD"
                    usd_pattern = rf"([\d\.]+)\s+([\d\s]+\.\d{{2}})\s*USD"
                    usd_matches = list(re.finditer(usd_pattern, search_text))

                    value_usd = None
                    for usd_match in usd_matches:
                        if usd_match.start() < available_match.start():
                            match_shares = Decimal(usd_match.group(1).strip())
                            # Check if this matches our available shares (within small tolerance)
                            if abs(match_shares - shares) < Decimal("0.001"):
                                value_str = usd_match.group(2).replace(" ", "").strip()
                                value_usd = Decimal(value_str)
                                break

                    # If we didn't find matching USD value, try getting from plan header
                    if not value_usd:
                        # Check if all shares are available (Locked shows 0)
                        locked_zero_pattern = r"Locked\s+0\s+0\.00\s*EUR"
                        if re.search(locked_zero_pattern, search_text):
                            # All shares available, use plan header value
                            plan_value_str = plan_match.group(1).replace(" ", "").strip()
                            value_usd = Decimal(plan_value_str)

                    if value_usd and value_usd > 0:
                        return PositionData(
                            symbol="SAP",
                            cusip=None,
                            security_name=f"{plan_name} - Shares",
                            security_type=security_type,
                            quantity=shares,
                            price=self._share_price_eur,
                            market_value=value_usd,
                            cost_basis=None,
                            asset_class="EQUITY",
                            is_vested=True,
                            row_index=row_index,
                            currency="USD",
                        )
                except (InvalidOperation, ValueError):
                    continue

            # Check for locked-only section (no Available pattern found, but has Locked)
            # This means no vested shares in this plan
            locked_only_pattern = r"Locked\s+(\d+)\s+([\d\s]+\.\d{2})\s*USD"
            if re.search(locked_only_pattern, search_text) and not available_match:
                # This plan has only locked shares, return None
                return None

        return None

    def _parse_european_number(self, value: str) -> Optional[Decimal]:
        """Parse a number that may use European formatting.

        European format uses space as thousands separator and comma/dot for decimals.
        Examples: "10 133.70" or "10 133,70"

        Args:
            value: String representation of number

        Returns:
            Decimal value or None if parsing fails
        """
        try:
            # Remove spaces (thousands separator)
            cleaned = value.replace(" ", "").strip()
            # Handle comma as decimal separator
            if "," in cleaned and "." not in cleaned:
                cleaned = cleaned.replace(",", ".")
            return Decimal(cleaned)
        except InvalidOperation:
            return None
