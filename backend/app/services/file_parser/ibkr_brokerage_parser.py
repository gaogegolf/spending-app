"""Interactive Brokers (IBKR) brokerage statement parser with multi-currency support."""

import re
from typing import List, Dict, Optional, Tuple
from datetime import date
from decimal import Decimal, InvalidOperation
import pdfplumber

from app.services.file_parser.brokerage_parser import (
    BaseBrokerageParser,
    BrokerageParseResult,
    PositionData,
    detect_account_type,
)


class IBKRBrokerageParser(BaseBrokerageParser):
    """Parser for Interactive Brokers activity statements.

    Supports both single-account and multi-account statements.
    Multi-account statements have an "Account Summary" section on the first page
    followed by separate activity statements for each account.
    """

    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.provider = "ibkr"
        self.base_currency = "USD"
        self.fx_rates: Dict[str, Decimal] = {}
        self.cash_by_currency: Dict[str, Decimal] = {}
        self._account_sections: List[str] = []  # For multi-account parsing
        self._current_section_text: Optional[str] = None  # Text for current account section

    def is_multi_account_statement(self) -> bool:
        """Check if this is a multi-account statement.

        Multi-account statements have an "Account Summary" section at the beginning
        with a table listing multiple accounts and their NAV values.

        Returns:
            True if this is a multi-account statement
        """
        if not self.full_text:
            self._open_pdf()

        # Look for "Account Summary" section with multiple account rows
        # Pattern: Account Summary followed by a table with account IDs
        has_summary = "Account Summary" in self.full_text

        # Count unique account IDs (pattern: U followed by digits)
        account_pattern = r"Account\s+(U\d{7,})"
        account_ids = set(re.findall(account_pattern, self.full_text))

        return has_summary and len(account_ids) > 1

    def get_account_count(self) -> int:
        """Get the number of accounts in the statement.

        Returns:
            Number of unique accounts found
        """
        if not self.full_text:
            self._open_pdf()

        account_pattern = r"Account\s+(U\d{7,})"
        account_ids = set(re.findall(account_pattern, self.full_text))
        return len(account_ids)

    def _split_by_accounts(self) -> List[Tuple[str, str, str]]:
        """Split the full text into sections by account.

        Each account section starts with "Account Information" and contains
        account-specific data.

        Returns:
            List of tuples: (account_id, account_alias, section_text)
        """
        if not self.full_text:
            self._open_pdf()

        sections = []

        # Find all "Account Information" sections
        # Each section starts with "Account Information" and ends before the next
        # "Account Information" or at the end of the document
        section_pattern = r"Account Information\s*\n(.*?)(?=Account Information|$)"
        matches = list(re.finditer(section_pattern, self.full_text, re.DOTALL))

        for i, match in enumerate(matches):
            section_text = match.group(0)

            # Extract account ID from this section
            account_match = re.search(r"Account\s+(U\d{7,})", section_text)
            account_id = account_match.group(1) if account_match else f"Unknown_{i}"

            # Extract account alias
            alias_match = re.search(r"Account Alias\s+([A-Za-z0-9_-]+)", section_text)
            account_alias = alias_match.group(1) if alias_match else ""

            sections.append((account_id, account_alias, section_text))

        return sections

    def parse_all(self) -> List[BrokerageParseResult]:
        """Parse all accounts in the statement.

        For single-account statements, returns a list with one result.
        For multi-account statements, returns a result for each account.

        Returns:
            List of BrokerageParseResult objects, one per account
        """
        try:
            self._open_pdf()

            if not self.is_multi_account_statement():
                # Single account - use regular parse
                result = self._parse_single_account(self.full_text)
                return [result]

            # Multi-account statement - parse each section
            results = []
            sections = self._split_by_accounts()

            for account_id, account_alias, section_text in sections:
                # Reset per-account state
                self.fx_rates = {}
                self.cash_by_currency = {}
                self._current_section_text = section_text

                result = self._parse_single_account(section_text, account_id, account_alias)
                results.append(result)

            return results

        finally:
            self._close_pdf()

    def parse(self) -> BrokerageParseResult:
        """Parse IBKR statement and return holdings snapshot for first/only account.

        For multi-account statements, use parse_all() to get all accounts.
        """
        try:
            self._open_pdf()
            return self._parse_single_account(self.full_text)
        finally:
            self._close_pdf()

    def _parse_single_account(
        self,
        section_text: str,
        account_id: Optional[str] = None,
        account_alias: Optional[str] = None
    ) -> BrokerageParseResult:
        """Parse a single account section from IBKR statement.

        Args:
            section_text: The text for this account's section
            account_id: Pre-extracted account ID (for multi-account)
            account_alias: Pre-extracted account alias (for multi-account)

        Returns:
            BrokerageParseResult with holdings snapshot
        """
        errors = []
        warnings = []

        # Store section text for helper methods to use
        self._current_section_text = section_text

        try:
            # Detect account type from section
            self.account_type = detect_account_type(section_text, self.provider)

            # Extract account info (use provided or extract from section)
            if account_id:
                account_identifier = f"****{account_id[-4:]}"
            else:
                account_identifier = self._extract_account_identifier(section_text)

            self.base_currency = self._extract_base_currency(section_text)

            # Extract statement dates
            statement_date, statement_start_date = self._extract_statement_dates(section_text)

            # Extract FX rates first (needed for USD conversion)
            self._extract_fx_rates(section_text)

            # Extract totals
            total_value, total_cash, total_securities = self._extract_totals(section_text)

            # Extract positions
            positions = self._extract_positions(section_text)

            # Extract cash by currency
            self._extract_cash_balances(section_text)

            # Calculate total from positions for reconciliation
            calculated_total = self._calculate_total_usd(positions)

            # Reconcile
            is_reconciled, reconciliation_diff = self._reconcile(
                total_value, calculated_total, tolerance=Decimal("0.02")  # 2% tolerance for IBKR
            )

            if not is_reconciled:
                warnings.append(
                    f"Reconciliation difference: reported ${total_value} vs calculated ${calculated_total} "
                    f"(diff: ${reconciliation_diff})"
                )

            return BrokerageParseResult(
                success=True,
                provider=self.provider,
                account_type=self.account_type or "BROKERAGE",
                account_identifier=account_identifier,
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
                    "base_currency": self.base_currency,
                    "fx_rates": {k: str(v) for k, v in self.fx_rates.items()},
                    "cash_by_currency": {k: str(v) for k, v in self.cash_by_currency.items()},
                    "account_alias": account_alias or "",
                },
                base_currency=self.base_currency,
                fx_rates=self.fx_rates,
                cash_by_currency=self.cash_by_currency,
            )

        except Exception as e:
            errors.append(f"Failed to parse IBKR statement: {str(e)}")
            return BrokerageParseResult(
                success=False,
                provider=self.provider,
                account_type="BROKERAGE",
                account_identifier=account_id or "",
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
                base_currency="USD",
                fx_rates={},
                cash_by_currency={},
            )

    def _extract_account_identifier(self, section_text: Optional[str] = None) -> str:
        """Extract account identifier from IBKR statement."""
        text = section_text or self.full_text
        # Pattern: Account U6301776
        pattern = r"Account\s+([A-Z]\d{7,})"
        match = re.search(pattern, text)
        if match:
            account_id = match.group(1)
            # Mask the account ID
            return f"****{account_id[-4:]}"
        return "****0000"

    def _extract_base_currency(self, section_text: Optional[str] = None) -> str:
        """Extract base currency from IBKR statement."""
        text = section_text or self.full_text
        # Pattern: Base Currency USD
        pattern = r"Base Currency\s+([A-Z]{3})"
        match = re.search(pattern, text)
        if match:
            return match.group(1)
        return "USD"

    def _extract_statement_dates(self, section_text: Optional[str] = None) -> Tuple[Optional[date], Optional[date]]:
        """Extract statement date range from IBKR statement."""
        text = section_text or self.full_text
        # Pattern: December 1, 2025 - December 31, 2025
        pattern = r"(\w+)\s+(\d{1,2}),\s+(\d{4})\s*-\s*(\w+)\s+(\d{1,2}),\s+(\d{4})"
        match = re.search(pattern, text)

        if match:
            month_names = {
                "January": 1, "February": 2, "March": 3, "April": 4,
                "May": 5, "June": 6, "July": 7, "August": 8,
                "September": 9, "October": 10, "November": 11, "December": 12
            }
            try:
                start_month = month_names.get(match.group(1), 1)
                start_day = int(match.group(2))
                start_year = int(match.group(3))
                end_month = month_names.get(match.group(4), 12)
                end_day = int(match.group(5))
                end_year = int(match.group(6))

                statement_start = date(start_year, start_month, start_day)
                statement_date = date(end_year, end_month, end_day)
                return statement_date, statement_start
            except (ValueError, KeyError):
                pass

        return None, None

    def _extract_totals(self, section_text: Optional[str] = None) -> Tuple[Decimal, Decimal, Decimal]:
        """Extract total values from Net Asset Value section."""
        text = section_text or self.full_text
        total_value = Decimal("0")
        total_cash = Decimal("0")
        total_securities = Decimal("0")

        # Look for the NAV Total line (December column)
        # Pattern: Total 77,254.27 150,518.12 -70,319.04 80,199.08 2,944.81
        # The fourth number after "Total" is the current total
        total_pattern = r"Total\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)"
        match = re.search(total_pattern, text)
        if match:
            try:
                total_value = self._parse_decimal(match.group(4))
            except (ValueError, InvalidOperation):
                pass

        # Look for Cash total
        # Pattern: Cash 17,231.91 82,433.43 -70,119.68 12,313.75
        cash_pattern = r"Cash\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)"
        match = re.search(cash_pattern, text)
        if match:
            try:
                total_cash = self._parse_decimal(match.group(4))
            except (ValueError, InvalidOperation):
                pass

        # Look for Stock total
        # Pattern: Stock 60,107.41 67,952.21 0.00 67,952.21
        stock_pattern = r"Stock\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)\s+([\d,.-]+)"
        match = re.search(stock_pattern, text)
        if match:
            try:
                total_securities = self._parse_decimal(match.group(4))
            except (ValueError, InvalidOperation):
                pass

        return total_value, total_cash, total_securities

    def _extract_fx_rates(self, section_text: Optional[str] = None) -> None:
        """Extract FX rates from the Forex Balances section.

        The Forex Balances section contains reliable FX rates in the Close Price column.
        Format: Currency Quantity Cost_Price Cost_Basis_USD Close_Price Value_USD
        Example: EUR -59,696.65 1.124348286 67,119.82 1.1746 -70,119
        """
        text = section_text or self.full_text

        # Look specifically in the Forex Balances section
        # Find the section between "Forex Balances" and the next section
        forex_section_match = re.search(
            r"Forex Balances.*?Description\s+Quantity\s+Cost Price.*?Forex\s*USD(.*?)(?:Total|Trades|\n\n)",
            text,
            re.DOTALL | re.IGNORECASE
        )

        if forex_section_match:
            forex_text = forex_section_match.group(1)
            # Pattern: EUR -59,696.65 1.124348286 67,119.82 1.1746 -70,119
            # The Close Price is the 4th number after the currency
            rate_pattern = r"(EUR|HKD|GBP|JPY|CHF|CAD|AUD)\s+([\d,.-]+)\s+([\d.]+)\s+([\d,.-]+)\s+([\d.]+)"
            matches = re.findall(rate_pattern, forex_text)
            for match in matches:
                currency, quantity, cost_price, cost_basis, close_price = match
                if currency != "USD":
                    try:
                        rate = Decimal(close_price)
                        self.fx_rates[currency] = rate
                    except (ValueError, InvalidOperation):
                        pass

        # If we didn't find rates in Forex Balances, try the Mark-to-Market Performance Summary
        if not self.fx_rates:
            # Pattern in M2M: EUR -45,429.04 -59,696.65 1.1597 1.1746
            # Prior quantity, current quantity, prior price, current price
            m2m_pattern = r"(EUR|HKD|GBP|JPY|CHF|CAD|AUD)\s+[\d,.-]+\s+[\d,.-]+\s+[\d.]+\s+([\d.]+)"
            matches = re.findall(m2m_pattern, text)
            for match in matches:
                currency, rate_str = match
                if currency != "USD":
                    try:
                        rate = Decimal(rate_str)
                        # Only use rates that look reasonable (between 0.01 and 1000)
                        if Decimal("0.01") <= rate <= Decimal("1000"):
                            self.fx_rates[currency] = rate
                    except (ValueError, InvalidOperation):
                        pass

        # USD rate is always 1.0
        self.fx_rates["USD"] = Decimal("1.0")

    def _extract_cash_balances(self, section_text: Optional[str] = None) -> None:
        """Extract cash balances by currency from Forex Balances section."""
        text = section_text or self.full_text
        # Pattern in Forex Balances: EUR -59,696.65 1.124348286 67,119.82 1.1746 -70,119
        # The quantity is the second number after the currency

        forex_balance_pattern = r"(EUR|HKD|USD|GBP|JPY|CHF|CAD|AUD)\s+([\d,.-]+)\s+[\d.]+\s+"
        matches = re.findall(forex_balance_pattern, text)

        for match in matches:
            currency, amount_str = match
            try:
                amount = self._parse_decimal(amount_str)
                self.cash_by_currency[currency] = amount
            except (ValueError, InvalidOperation):
                pass

    def _extract_positions(self, section_text: Optional[str] = None) -> List[PositionData]:
        """Extract positions from Open Positions section."""
        text = section_text or self.full_text
        positions = []
        row_index = 0

        # Look for Open Positions section
        # The format varies, but typically: Symbol Quantity Mult Cost Price Cost Basis Close Price Value
        # Under currency headers (EUR, HKD, USD)

        # First, try to find positions with currency context
        # Pattern: FLOW 2,303 1 23.321312777 53,708.98 25.1200 57,851
        position_pattern = r"([A-Z0-9]{2,10})\s+(\d[\d,]*)\s+1\s+([\d.]+)\s+([\d,.-]+)\s+([\d.]+)\s+([\d,.-]+)"

        # First, find the Open Positions section
        open_pos_match = re.search(
            r"Open Positions.*?Symbol.*?Stocks\s*(.*?)(?:Total Stocks in USD|Forex Balances|Financial Instrument|$)",
            text, re.DOTALL
        )

        if open_pos_match:
            open_positions_text = open_pos_match.group(1)

            # Define currencies to look for - pattern matches currency header followed by stock entries
            # Currency appears on its own line, followed by stock entries until "Total"
            currencies = ["EUR", "AUD", "CAD", "HKD", "GBP", "USD"]

            for currency in currencies:
                # Pattern: currency header, then stock entries until "Total"
                # The currency line is followed by stock data
                # Use (?:^|\n) to match currency at start of text OR after newline
                currency_pattern = rf"(?:^|\n){currency}\n(.*?)(?:\nTotal\b|\n(?:EUR|AUD|CAD|HKD|GBP|USD)\n|$)"
                currency_match = re.search(currency_pattern, open_positions_text, re.DOTALL | re.MULTILINE)

                if currency_match:
                    currency_text = currency_match.group(1)
                    # Find stock entries
                    stock_matches = re.findall(position_pattern, currency_text)
                    for match in stock_matches:
                        symbol, qty_str, cost_price, cost_basis, close_price, value_str = match
                        try:
                            quantity = self._parse_decimal(qty_str)
                            price = self._parse_decimal(close_price)
                            market_value = self._parse_decimal(value_str)
                            cost = self._parse_decimal(cost_basis)

                            # Get FX rate for this currency
                            fx_rate = self.fx_rates.get(currency, Decimal("1.0"))
                            market_value_usd = market_value * fx_rate

                            positions.append(PositionData(
                                symbol=symbol,
                                cusip=None,
                                security_name=symbol,  # Will be updated from Financial Instrument Info
                                security_type="STOCK",
                                quantity=quantity,
                                price=price,
                                market_value=market_value,
                                cost_basis=cost,
                                asset_class="EQUITY",
                                row_index=row_index,
                                currency=currency,
                                market_value_usd=market_value_usd,
                                fx_rate_used=fx_rate,
                            ))
                            row_index += 1
                        except (ValueError, InvalidOperation):
                            pass

        # Fallback: Look for USD positions using original pattern (if no positions found)
        if not positions:
            usd_section = re.search(r"Stocks\s*USD\s*(.*?)(?:Total|EUR|HKD|AUD|CAD|$)", text, re.DOTALL)
            if usd_section:
                usd_text = usd_section.group(1)
                matches = re.findall(position_pattern, usd_text)
                for match in matches:
                    symbol, qty_str, cost_price, cost_basis, close_price, value_str = match
                    try:
                        quantity = self._parse_decimal(qty_str)
                        price = self._parse_decimal(close_price)
                        market_value = self._parse_decimal(value_str)
                        cost = self._parse_decimal(cost_basis)

                        positions.append(PositionData(
                            symbol=symbol,
                            cusip=None,
                            security_name=symbol,
                            security_type="STOCK",
                            quantity=quantity,
                            price=price,
                            market_value=market_value,
                            cost_basis=cost,
                            asset_class="EQUITY",
                            row_index=row_index,
                            currency="USD",
                            market_value_usd=market_value,
                            fx_rate_used=Decimal("1.0"),
                        ))
                        row_index += 1
                    except (ValueError, InvalidOperation):
                        pass

        # Try alternative pattern for Total in USD line
        # Total in USD 63,086.57 67,952
        if not positions:
            # Try simpler pattern from Open Positions
            simple_pattern = r"([A-Z]{2,6})\s+(\d[\d,]*)\s+1\s+([\d.]+)\s+([\d,.-]+)\s+([\d.]+)\s+([\d,.-]+)"
            matches = re.findall(simple_pattern, text)
            for match in matches:
                symbol, qty_str, cost_price_str, cost_basis_str, close_price_str, value_str = match
                # Skip if it looks like a forex entry (negative quantities or weird symbols)
                if symbol in ["EUR", "HKD", "USD", "GBP", "JPY"]:
                    continue
                try:
                    quantity = self._parse_decimal(qty_str)
                    if quantity <= 0:
                        continue
                    price = self._parse_decimal(close_price_str)
                    market_value = self._parse_decimal(value_str)
                    cost = self._parse_decimal(cost_basis_str)

                    positions.append(PositionData(
                        symbol=symbol,
                        cusip=None,
                        security_name=symbol,
                        security_type="STOCK",
                        quantity=quantity,
                        price=price,
                        market_value=market_value,
                        cost_basis=cost,
                        asset_class="EQUITY",
                        row_index=row_index,
                        currency="USD",
                        market_value_usd=market_value,
                        fx_rate_used=Decimal("1.0"),
                    ))
                    row_index += 1
                except (ValueError, InvalidOperation):
                    pass

        # Update security names from Financial Instrument Information section
        self._update_security_names(positions, text)

        return positions

    def _update_security_names(self, positions: List[PositionData], section_text: Optional[str] = None) -> None:
        """Update position security names from Financial Instrument Information section."""
        text = section_text or self.full_text
        # Pattern: 2689 NINE DRAGONS PAPER HOLDINGS 42446354
        # Pattern: FLOW FLOW TRADERS LTD 607961218
        name_pattern = r"([A-Z0-9]{2,10})\s+([A-Z][A-Za-z\s&.'()-]+?)\s+\d{6,}"

        matches = re.findall(name_pattern, text)
        name_map = {}
        for match in matches:
            symbol, name = match
            name = name.strip()
            if len(name) > 3:  # Filter out short matches
                name_map[symbol] = name

        for position in positions:
            if position.symbol in name_map:
                position.security_name = name_map[position.symbol]

    def _calculate_total_usd(self, positions: List[PositionData]) -> Decimal:
        """Calculate total in USD from positions and cash."""
        position_total = Decimal("0")
        for p in positions:
            if p.market_value_usd:
                position_total += p.market_value_usd
            elif p.currency == "USD":
                position_total += p.market_value
            else:
                # Convert using FX rate
                fx_rate = self.fx_rates.get(p.currency, Decimal("1.0"))
                position_total += p.market_value * fx_rate

        # Add cash in USD
        cash_total = Decimal("0")
        for currency, amount in self.cash_by_currency.items():
            fx_rate = self.fx_rates.get(currency, Decimal("1.0"))
            cash_total += amount * fx_rate

        return position_total + cash_total

    def _parse_decimal(self, value: str) -> Decimal:
        """Parse a string to Decimal, handling commas and negative values."""
        if not value:
            return Decimal("0")
        # Remove commas and whitespace
        clean = value.replace(",", "").replace(" ", "").strip()
        # Handle parentheses for negative numbers
        if clean.startswith("(") and clean.endswith(")"):
            clean = "-" + clean[1:-1]
        return Decimal(clean)
