"""Fidelity brokerage statement parser."""

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


class FidelityBrokerageParser(BaseBrokerageParser):
    """Parser for Fidelity brokerage statements.

    Supports both single-account and multi-account statements.
    Multi-account statements have an "Accounts Included in This Report" table
    listing multiple accounts with their page numbers.
    """

    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.provider = "fidelity"
        self._account_sections: List[dict] = []  # For multi-account parsing
        self._current_section_pages: Optional[List[int]] = None  # Pages for current account

    def is_multi_account_statement(self) -> bool:
        """Check if this is a multi-account statement.

        Multi-account statements have an "Accounts Included in This Report" table
        with multiple account entries.

        Returns:
            True if this is a multi-account statement
        """
        if not self.full_text:
            self._open_pdf()

        # Look for "Accounts Included in This Report" section
        if "Accounts Included in This Report" not in self.full_text:
            return False

        # Parse the accounts table to count entries
        accounts = self._parse_accounts_table()
        return len(accounts) > 1

    def get_account_count(self) -> int:
        """Get the number of accounts in the statement.

        Returns:
            Number of unique accounts found
        """
        if not self.full_text:
            self._open_pdf()

        accounts = self._parse_accounts_table()
        return len(accounts)

    @staticmethod
    def _extract_holder_from_account_name(account_name: str) -> Optional[str]:
        """Extract holder name from Fidelity account table name.

        Examples:
            "FIDELITY ROTH IRA XINZHU CAI - ROTH INDIVIDUAL" → "XINZHU CAI"
            "FIDELITY BROKERAGE GE GAO - INDIVIDUAL" → "GE GAO"
        """
        # Pattern: everything after "IRA|BROKERAGE|ACCOUNT" and before " - "
        match = re.search(
            r'(?:IRA|BROKERAGE|ACCOUNT)\s+([A-Z][A-Z\s]+?)\s+-\s+',
            account_name, re.IGNORECASE
        )
        if match:
            name = match.group(1).strip()
            # Validate: 2-3 words, all caps
            words = name.split()
            if 2 <= len(words) <= 3 and all(w.isalpha() for w in words):
                return name
        return None

    def _extract_holder_from_text(self) -> Optional[str]:
        """Extract holder name from full statement text (single-account fallback)."""
        # Look for pattern in accounts table section
        pattern = r'(?:IRA|BROKERAGE|ACCOUNT)\s+([A-Z][A-Z\s]+?)\s+-\s+'
        match = re.search(pattern, self.full_text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            words = name.split()
            if 2 <= len(words) <= 3 and all(w.isalpha() for w in words):
                return name
        return None

    def _parse_accounts_table(self) -> List[dict]:
        """Parse the 'Accounts Included in This Report' table.

        Returns:
            List of dicts with account info: page, name, account_number, ending_value
        """
        accounts = []

        # Pattern for account rows in the table:
        # 4  FIDELITY TRADITIONAL IRA XINZHU CAI - TRADITIONAL IRA  226-722819       $12.49           $13.30
        # 7  FIDELITY ROTH IRA XINZHU CAI - ROTH INDIVIDUAL        231-489641   177,090.28      187,294.96
        # The page number is at the start, followed by account name, account number, values
        pattern = r"(\d+)\s+(FIDELITY[A-Z\s]+(?:IRA|BROKERAGE|ACCOUNT)[^0-9]+)(\d{3}-\d{6})\s+\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.?\d*)"

        matches = re.findall(pattern, self.full_text, re.IGNORECASE)

        for match in matches:
            page_num, account_name, account_number, beginning_value, ending_value = match
            accounts.append({
                "page": int(page_num),
                "name": account_name.strip(),
                "account_number": account_number,
                "beginning_value": beginning_value.replace(",", ""),
                "ending_value": ending_value.replace(",", ""),
            })

        # Sort by page number
        accounts.sort(key=lambda x: x["page"])

        return accounts

    def _get_pages_for_account(self, account_index: int, accounts: List[dict]) -> List[int]:
        """Get the page range for a specific account.

        Args:
            account_index: Index of the account in accounts list
            accounts: List of account info dicts

        Returns:
            List of page numbers (0-indexed) for this account
        """
        if not accounts or account_index >= len(accounts):
            return []

        start_page = accounts[account_index]["page"] - 1  # Convert to 0-indexed

        # End page is either the start of next account or end of PDF
        if account_index + 1 < len(accounts):
            end_page = accounts[account_index + 1]["page"] - 1
        else:
            end_page = len(self.pdf.pages)

        return list(range(start_page, end_page))

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
                result = self._parse_with_pages(None)
                return [result]

            # Multi-account statement - parse each account section
            results = []
            accounts = self._parse_accounts_table()

            for i, account_info in enumerate(accounts):
                pages = self._get_pages_for_account(i, accounts)
                self._current_section_pages = pages

                # Extract text for just these pages
                section_text = self._get_text_for_pages(pages)

                result = self._parse_single_account(
                    section_text,
                    pages,
                    account_info["account_number"],
                    account_info["ending_value"],
                    account_table_name=account_info.get("name"),
                )
                results.append(result)

            return results

        finally:
            self._close_pdf()

    def _get_text_for_pages(self, pages: List[int]) -> str:
        """Extract text from specific pages.

        Args:
            pages: List of page indices (0-indexed)

        Returns:
            Concatenated text from specified pages
        """
        text_parts = []
        for page_idx in pages:
            if 0 <= page_idx < len(self.pdf.pages):
                page_text = self.pdf.pages[page_idx].extract_text() or ""
                text_parts.append(page_text)
        return "\n".join(text_parts)

    def _parse_single_account(
        self,
        section_text: str,
        pages: List[int],
        account_number: str,
        expected_value: str,
        account_table_name: Optional[str] = None,
    ) -> BrokerageParseResult:
        """Parse a single account section from Fidelity statement.

        Args:
            section_text: The text for this account's section
            pages: Page indices for this account
            account_number: The account number (e.g., "231-489641")
            expected_value: Expected ending value for validation

        Returns:
            BrokerageParseResult with holdings snapshot
        """
        errors = []
        warnings = []

        try:
            # Detect account type from section text
            account_type = detect_account_type(section_text, self.provider)

            # Mask account number
            account_identifier = f"****{account_number[-4:]}" if len(account_number) >= 4 else account_number

            # Extract statement dates (should be same across accounts)
            statement_date, statement_start_date = self._extract_statement_dates_from_text(section_text)
            if not statement_date:
                # Fall back to full text
                statement_date, statement_start_date = self._extract_statement_dates()

            # Extract cash/securities breakdowns from section text
            _, total_cash, total_securities = self._extract_totals_from_text(section_text)

            # Use the per-account ending value from the accounts table as the
            # authoritative total. The section text may contain the combined
            # statement total (e.g. "Your Account Value") which is wrong for
            # individual accounts in a multi-account statement.
            total_value = Decimal("0")
            if expected_value:
                try:
                    total_value = Decimal(expected_value.replace(",", ""))
                except InvalidOperation:
                    pass

            # Fall back to section text extraction only if no expected value
            if total_value == Decimal("0"):
                total_value, _, _ = self._extract_totals_from_text(section_text)

            # Extract positions from pages
            positions = self._extract_positions_from_pages(pages)

            # Reconciliation: add cash if not already captured as a position
            calculated_total = self._calculate_total(positions)
            cash_in_positions = any(p.asset_class == "CASH" for p in positions)
            reconcile_total = calculated_total if cash_in_positions else calculated_total + total_cash
            is_reconciled, reconciliation_diff = self._reconcile(total_value, reconcile_total)

            if not is_reconciled:
                warnings.append(
                    f"Reconciliation warning: calculated total ${reconcile_total} differs from "
                    f"reported total ${total_value} by ${reconciliation_diff}"
                )

            return BrokerageParseResult(
                success=True,
                provider=self.provider,
                account_type=account_type,
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
                account_number_raw=account_number,
                raw_metadata={
                    "pages": len(pages),
                    "position_count": len(positions),
                    "account_number": account_number,
                    "account_holder_name": self._extract_holder_from_account_name(account_table_name) if account_table_name else None,
                },
            )

        except Exception as e:
            errors.append(f"Failed to parse Fidelity account {account_number}: {str(e)}")
            return BrokerageParseResult(
                success=False,
                provider=self.provider,
                account_type="BROKERAGE",
                account_identifier=f"****{account_number[-4:]}" if len(account_number) >= 4 else "",
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

    def _extract_statement_dates_from_text(self, text: str) -> Tuple[Optional[date], Optional[date]]:
        """Extract statement dates from a text section."""
        # Try "Month Day, Year - Month Day, Year" format
        date_range_pattern = r"(\w+\s+\d{1,2},\s+\d{4})\s*[-–]\s*(\w+\s+\d{1,2},\s+\d{4})"
        match = re.search(date_range_pattern, text)

        if match:
            start_str = match.group(1)
            end_str = match.group(2)
            try:
                start_date = datetime.strptime(start_str, "%B %d, %Y").date()
                end_date = datetime.strptime(end_str, "%B %d, %Y").date()
                return end_date, start_date
            except ValueError:
                pass

        return None, None

    def _extract_totals_from_text(self, text: str) -> Tuple[Decimal, Decimal, Decimal]:
        """Extract totals from a text section."""
        total_value = Decimal("0")
        total_cash = Decimal("0")
        total_securities = Decimal("0")

        # Extract total account value
        value_patterns = [
            r"Your\s+Account\s+Value[:\s]*\$?([\d,]+\.?\d*)",
            r"Ending\s+Account\s+Value[:\s]*\$?([\d,]+\.?\d*)",
            r"Account\s+Value[:\s]*\$?([\d,]+\.?\d*)",
        ]

        for pattern in value_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    total_value = Decimal(match.group(1).replace(",", ""))
                    break
                except InvalidOperation:
                    continue

        # Extract Core Account (cash) total
        cash_pattern = r"Total\s+Core\s+Account[^$]*\$[\d,]+\.?\d*[^$]*\$([\d,]+\.?\d*)"
        match = re.search(cash_pattern, text, re.IGNORECASE)
        if match:
            try:
                total_cash = Decimal(match.group(1).replace(",", ""))
            except InvalidOperation:
                pass

        # Extract securities total
        securities_pattern = r"Total\s+Exchange\s+Traded\s+Products[^$]*\$[\d,]+\.?\d*[^$]*\$([\d,]+\.?\d*)"
        match = re.search(securities_pattern, text, re.IGNORECASE)
        if match:
            try:
                total_securities = Decimal(match.group(1).replace(",", ""))
            except InvalidOperation:
                pass

        return total_value, total_cash, total_securities

    def _extract_positions_from_pages(self, pages: List[int]) -> List[PositionData]:
        """Extract positions from specific pages.

        Args:
            pages: List of page indices (0-indexed)

        Returns:
            List of PositionData objects
        """
        positions = []
        row_index = 0

        for page_idx in pages:
            if 0 <= page_idx < len(self.pdf.pages):
                page = self.pdf.pages[page_idx]
                tables = page.extract_tables()

                for table in tables:
                    if not table:
                        continue

                    # Check if this looks like a holdings table
                    header_row = table[0] if table else []
                    if not self._is_holdings_table(header_row):
                        continue

                    # Parse holdings rows
                    for row in table[1:]:
                        position = self._parse_holdings_row(row, row_index)
                        if position:
                            positions.append(position)
                            row_index += 1

        # If no tables found, try text extraction
        if not positions:
            section_text = self._get_text_for_pages(pages)
            positions = self._extract_positions_from_section_text(section_text)

        return positions

    def _extract_positions_from_section_text(self, section_text: str) -> List[PositionData]:
        """Extract positions from text when table extraction fails."""
        positions = []
        row_index = 0
        lines = section_text.split('\n')

        # Pattern for holdings lines with multiple numbers
        # Security name may include symbol in parentheses like "TESLA INC COM (TSLA)"
        holdings_pattern = re.compile(
            r'^([A-Z][A-Z0-9\s&\'\-]+(?:\s*\([A-Z]{1,5}\))?)\s+'
            r'\$?([\d,]+\.?\d{0,2})\s+'
            r'([\d,]+\.?\d{0,4})\s+'
            r'\$?([\d,]+\.?\d{0,4})\s+'
            r'\$?([\d,]+\.?\d{0,2})\s+'
            r'\$?([\d,]+\.?\d{0,2})\s+'
            r'-?\$?([\d,]+\.?\d{0,2})'
        )

        symbol_pattern = re.compile(r'\(([A-Z]{1,5})\)')

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if any(skip in line.lower() for skip in ['total', 'subtotal', 'description', 'beginning', 'continued', 'page ', 'account']):
                i += 1
                continue

            match = holdings_pattern.match(line)
            if match:
                security_name = match.group(1).strip()

                # First, check if symbol is embedded in the security name
                symbol = None
                embedded_symbol = symbol_pattern.search(security_name)
                if embedded_symbol:
                    symbol = embedded_symbol.group(1)
                    # Remove symbol from security name for cleaner display
                    security_name = re.sub(r'\s*\([A-Z]{1,5}\)\s*', '', security_name).strip()
                else:
                    # Check next 2 lines for symbol
                    for j in range(1, 3):
                        if i + j < len(lines):
                            next_line = lines[i + j].strip()
                            symbol_match = symbol_pattern.search(next_line)
                            if symbol_match:
                                symbol = symbol_match.group(1)
                                break

                try:
                    quantity = Decimal(match.group(3).replace(",", ""))
                    price = Decimal(match.group(4).replace(",", ""))
                    market_value = Decimal(match.group(5).replace(",", ""))
                    cost_basis_str = match.group(6).replace(",", "")
                    cost_basis = Decimal(cost_basis_str) if cost_basis_str else None

                    if market_value > 0:
                        security_type = self._classify_security_type(security_name, symbol)
                        asset_class = self._classify_asset_class(security_type, security_name)

                        positions.append(PositionData(
                            symbol=symbol,
                            cusip=None,
                            security_name=security_name,
                            security_type=security_type,
                            quantity=quantity,
                            price=price,
                            market_value=market_value,
                            cost_basis=cost_basis,
                            asset_class=asset_class,
                            row_index=row_index,
                        ))
                        row_index += 1
                except (InvalidOperation, IndexError):
                    pass

            i += 1

        return positions

    def _parse_with_pages(self, pages: Optional[List[int]]) -> BrokerageParseResult:
        """Parse statement using specific pages or all pages."""
        if pages is None:
            # Use all pages (single account mode)
            return self._parse_full_statement()
        else:
            # Use specific pages (multi-account mode)
            section_text = self._get_text_for_pages(pages)
            # Extract account number from section
            pattern = r"Account\s*(?:Number|#)[:\s]*([A-Z]?\d{2,3}-\d{6})"
            match = re.search(pattern, section_text, re.IGNORECASE)
            account_number = match.group(1) if match else "Unknown"

            return self._parse_single_account(section_text, pages, account_number, "")

    def _parse_full_statement(self) -> BrokerageParseResult:
        """Parse the full statement (original single-account logic)."""
        errors = []
        warnings = []

        try:
            # Detect account type
            self.account_type = self.detect_account_type()

            # Extract data
            account_id = self._extract_account_identifier()
            statement_date, statement_start_date = self._extract_statement_dates()
            total_value, total_cash, total_securities = self._extract_totals()
            positions = self._extract_positions()

            # Reconciliation: add cash if not already captured as a position
            calculated_total = self._calculate_total(positions)
            cash_in_positions = any(p.asset_class == "CASH" for p in positions)
            reconcile_total = calculated_total if cash_in_positions else calculated_total + total_cash
            is_reconciled, reconciliation_diff = self._reconcile(total_value, reconcile_total)

            if not is_reconciled:
                warnings.append(
                    f"Reconciliation warning: calculated total ${reconcile_total} differs from "
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
                    "account_holder_name": self._extract_holder_from_text(),
                },
            )

        except Exception as e:
            errors.append(f"Failed to parse Fidelity statement: {str(e)}")
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

    def parse(self) -> BrokerageParseResult:
        """Parse Fidelity statement and return holdings snapshot."""
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

            # Reconciliation: add cash if not already captured as a position
            calculated_total = self._calculate_total(positions)
            cash_in_positions = any(p.asset_class == "CASH" for p in positions)
            reconcile_total = calculated_total if cash_in_positions else calculated_total + total_cash
            is_reconciled, reconciliation_diff = self._reconcile(total_value, reconcile_total)

            if not is_reconciled:
                warnings.append(
                    f"Reconciliation warning: calculated total ${reconcile_total} differs from "
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
                    "account_holder_name": self._extract_holder_from_text(),
                },
            )

        except Exception as e:
            errors.append(f"Failed to parse Fidelity statement: {str(e)}")
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
        """Extract masked account identifier from Fidelity statement.

        Fidelity account numbers are typically in format:
        - Z##-###### (e.g., Z09-403829)
        - ###-###### (e.g., 123-456789)
        """
        # Look for Account Number pattern
        pattern = r"Account\s*(?:Number|#)[:\s]*([A-Z]?\d{2,3}-\d{6})"
        match = re.search(pattern, self.full_text, re.IGNORECASE)

        if match:
            account_num = match.group(1)
            self._raw_account_number = account_num
            # Mask the account number, showing only last 4 digits
            if len(account_num) >= 4:
                return f"****{account_num[-4:]}"
            return account_num

        return "Unknown"

    def _extract_statement_dates(self) -> Tuple[Optional[date], Optional[date]]:
        """Extract statement date range from Fidelity statement.

        Looks for patterns like:
        - "December 1, 2025 - December 31, 2025"
        - "as of MM/DD/YYYY"
        """
        # Try "Month Day, Year - Month Day, Year" format
        date_range_pattern = r"(\w+\s+\d{1,2},\s+\d{4})\s*[-–]\s*(\w+\s+\d{1,2},\s+\d{4})"
        match = re.search(date_range_pattern, self.full_text)

        if match:
            start_str = match.group(1)
            end_str = match.group(2)
            try:
                start_date = datetime.strptime(start_str, "%B %d, %Y").date()
                end_date = datetime.strptime(end_str, "%B %d, %Y").date()
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
        """Extract total values from Fidelity statement.

        Looks for:
        - Your Account Value / Account Value / Ending Account Value
        - Core Account totals (cash)
        - Exchange Traded Products totals (securities)
        """
        total_value = Decimal("0")
        total_cash = Decimal("0")
        total_securities = Decimal("0")

        # Extract total account value
        # Pattern: "Your Account Value: $376,206.94" or "Account Value: $376,206.94"
        value_patterns = [
            r"Your\s+Account\s+Value[:\s]*\$?([\d,]+\.?\d*)",
            r"Ending\s+Account\s+Value[:\s]*\$?([\d,]+\.?\d*)",
            r"Account\s+Value[:\s]*\$?([\d,]+\.?\d*)",
        ]

        for pattern in value_patterns:
            match = re.search(pattern, self.full_text, re.IGNORECASE)
            if match:
                try:
                    total_value = Decimal(match.group(1).replace(",", ""))
                    break
                except InvalidOperation:
                    continue

        # Extract Core Account (cash) total
        # Pattern: "Total Core Account (3% of account holdings) $10,031.04 $11,601.16"
        cash_pattern = r"Total\s+Core\s+Account[^$]*\$[\d,]+\.?\d*[^$]*\$([\d,]+\.?\d*)"
        match = re.search(cash_pattern, self.full_text, re.IGNORECASE)
        if match:
            try:
                total_cash = Decimal(match.group(1).replace(",", ""))
            except InvalidOperation:
                pass

        # Extract Exchange Traded Products total (securities)
        # Pattern: "Total Exchange Traded Products (97% of account holdings) $361,539.92 $364,605.78"
        securities_pattern = r"Total\s+Exchange\s+Traded\s+Products[^$]*\$[\d,]+\.?\d*[^$]*\$([\d,]+\.?\d*)"
        match = re.search(securities_pattern, self.full_text, re.IGNORECASE)
        if match:
            try:
                total_securities = Decimal(match.group(1).replace(",", ""))
            except InvalidOperation:
                pass

        return total_value, total_cash, total_securities

    def _extract_positions(self) -> List[PositionData]:
        """Extract position/holdings data from Fidelity statement.

        Fidelity statements have holdings tables with columns:
        - Description (with symbol in parentheses)
        - Beginning Market Value
        - Quantity
        - Price Per Unit
        - Ending Market Value
        - Total Cost Basis
        - Unrealized Gain/Loss
        """
        positions = []
        row_index = 0

        # Extract from tables on holdings pages
        for page in self.pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue

                # Check if this looks like a holdings table
                header_row = table[0] if table else []
                if not self._is_holdings_table(header_row):
                    continue

                # Parse holdings rows
                for row in table[1:]:
                    position = self._parse_holdings_row(row, row_index)
                    if position:
                        positions.append(position)
                        row_index += 1

        # If no tables found, try text extraction
        if not positions:
            positions = self._extract_positions_from_text()

        return positions

    def _is_holdings_table(self, header_row: List) -> bool:
        """Check if this table header looks like a holdings table."""
        if not header_row:
            return False

        header_text = " ".join(str(cell or "").lower() for cell in header_row)
        indicators = ["description", "quantity", "market value", "price", "ending"]
        return sum(1 for ind in indicators if ind in header_text) >= 2

    def _parse_holdings_row(self, row: List, row_index: int) -> Optional[PositionData]:
        """Parse a single holdings table row into PositionData."""
        if not row or len(row) < 4:
            return None

        # Skip total/summary rows
        first_cell = str(row[0] or "").lower()
        if any(skip in first_cell for skip in ["total", "subtotal", "---", "continued"]):
            return None

        try:
            # Extract description and symbol
            description = str(row[0] or "").strip()
            if not description or description.lower() in ["description", ""]:
                return None

            symbol, security_name = self._parse_security_description(description)

            # Find quantity, price, market value columns
            # Typical structure: Description, Beginning Value, Quantity, Price, Ending Value, Cost Basis, Gain/Loss
            quantity = None
            price = None
            market_value = None
            cost_basis = None

            for i, cell in enumerate(row[1:], 1):
                cell_str = str(cell or "").strip()
                if not cell_str or cell_str == "-" or cell_str == "--":
                    continue

                value = self._parse_currency(cell_str)
                if value is None:
                    continue

                # Heuristics based on column position and value
                if i == 2 and "." in cell_str and value < 1000000:  # Quantity column
                    quantity = value
                elif i == 3 and value < 10000:  # Price column (usually < $10k)
                    price = value
                elif i == 4:  # Ending Market Value column
                    market_value = value
                elif i == 5:  # Cost Basis column
                    cost_basis = value

            if market_value is None or market_value == 0:
                return None

            # Determine security type and asset class
            security_type = self._classify_security_type(security_name, symbol)
            asset_class = self._classify_asset_class(security_type, security_name)

            return PositionData(
                symbol=symbol,
                cusip=None,
                security_name=security_name,
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
        """Extract positions from text when table extraction fails.

        Fidelity statements have holdings in format like:
        AVANTIS US SMALL CAP VALUE ETF 48,744.66 482.000 101.9800 49,154.36 40,705.13 8,449.23 777.13
        (AVUV) 1.580

        Where the numbers are: Beginning Value, Quantity, Price, Ending Value, Cost Basis, Gain/Loss, Est. Income
        The symbol often appears on the next line in parentheses.
        """
        positions = []
        row_index = 0
        lines = self.full_text.split('\n')

        # Pattern for holdings lines with multiple numbers
        # Name followed by Beginning Value, Quantity, Price, Ending Value, Cost Basis, Gain/Loss
        # Security name may include symbol in parentheses like "TESLA INC COM (TSLA)"
        holdings_pattern = re.compile(
            r'^([A-Z][A-Z0-9\s&\'\-]+(?:\s*\([A-Z]{1,5}\))?)\s+'  # Security name (may include symbol in parens)
            r'\$?([\d,]+\.?\d{0,2})\s+'    # Beginning market value
            r'([\d,]+\.?\d{0,4})\s+'       # Quantity (can have 4 decimals)
            r'\$?([\d,]+\.?\d{0,4})\s+'    # Price per unit
            r'\$?([\d,]+\.?\d{0,2})\s+'    # Ending market value
            r'\$?([\d,]+\.?\d{0,2})\s+'    # Cost basis
            r'-?\$?([\d,]+\.?\d{0,2})'     # Unrealized gain/loss
        )

        # Alternative pattern for cash/money market with simpler format
        cash_pattern = re.compile(
            r'^(FIDELITY[A-Z\s]+|FDIC[A-Z\s]+)\s+'
            r'\$?([\d,]+\.?\d{0,2})\s+'    # Beginning value
            r'\$?([\d,]+\.?\d{0,2})'       # Ending value
        )

        # Pattern to find symbol - can be in parentheses at start or anywhere in line
        symbol_pattern = re.compile(r'\(([A-Z]{1,5})\)')

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Skip header and summary lines
            if any(skip in line.lower() for skip in ['total', 'subtotal', 'description', 'beginning', 'continued', 'page ', 'account']):
                i += 1
                continue

            match = holdings_pattern.match(line)
            if match:
                security_name = match.group(1).strip()

                # First, check if symbol is embedded in the security name (e.g., "TESLA INC COM (TSLA)")
                symbol = None
                embedded_symbol = symbol_pattern.search(security_name)
                if embedded_symbol:
                    symbol = embedded_symbol.group(1)
                    # Remove symbol from security name for cleaner display
                    security_name = re.sub(r'\s*\([A-Z]{1,5}\)\s*', '', security_name).strip()
                else:
                    # Check next 2 lines for symbol (sometimes there's "USD" before symbol)
                    for j in range(1, 3):
                        if i + j < len(lines):
                            next_line = lines[i + j].strip()
                            symbol_match = symbol_pattern.search(next_line)
                            if symbol_match:
                                symbol = symbol_match.group(1)
                                break

                try:
                    quantity = Decimal(match.group(3).replace(",", ""))
                    price = Decimal(match.group(4).replace(",", ""))
                    market_value = Decimal(match.group(5).replace(",", ""))
                    cost_basis_str = match.group(6).replace(",", "")
                    cost_basis = Decimal(cost_basis_str) if cost_basis_str else None

                    if market_value > 0:
                        security_type = self._classify_security_type(security_name, symbol)
                        asset_class = self._classify_asset_class(security_type, security_name)

                        positions.append(PositionData(
                            symbol=symbol,
                            cusip=None,
                            security_name=security_name,
                            security_type=security_type,
                            quantity=quantity,
                            price=price,
                            market_value=market_value,
                            cost_basis=cost_basis,
                            asset_class=asset_class,
                            row_index=row_index,
                        ))
                        row_index += 1
                except (InvalidOperation, IndexError):
                    pass

            # Try cash pattern for money market/FDIC accounts
            elif cash_pattern.match(line):
                cash_match = cash_pattern.match(line)
                security_name = cash_match.group(1).strip()

                # Check next 2 lines for symbol (sometimes there's "USD" before symbol)
                symbol = None
                for j in range(1, 3):
                    if i + j < len(lines):
                        next_line = lines[i + j].strip()
                        symbol_match = symbol_pattern.search(next_line)
                        if symbol_match:
                            symbol = symbol_match.group(1)
                            break

                try:
                    market_value = Decimal(cash_match.group(3).replace(",", ""))

                    if market_value > 0:
                        positions.append(PositionData(
                            symbol=symbol,
                            cusip=None,
                            security_name=security_name,
                            security_type="MONEY_MARKET",
                            quantity=market_value,  # For cash, quantity = value
                            price=Decimal("1.00"),
                            market_value=market_value,
                            cost_basis=None,
                            asset_class="CASH",
                            row_index=row_index,
                        ))
                        row_index += 1
                except (InvalidOperation, IndexError):
                    pass

            i += 1

        return positions

    def _parse_security_description(self, description: str) -> Tuple[Optional[str], str]:
        """Parse security description to extract symbol and name.

        Examples:
        - "AVANTIS US SMALL CAP VALUE ETF (AVUV)" -> ("AVUV", "AVANTIS US SMALL CAP VALUE ETF")
        - "FIDELITY GOVERNMENT MONEY MARKET (SPAXX)" -> ("SPAXX", "FIDELITY GOVERNMENT MONEY MARKET")
        """
        # Look for symbol in parentheses
        symbol_match = re.search(r"\(([A-Z]{1,5})\)", description)
        if symbol_match:
            symbol = symbol_match.group(1)
            name = re.sub(r"\s*\([A-Z]{1,5}\)\s*", "", description).strip()
            return symbol, name

        return None, description.strip()

    def _parse_currency(self, value_str: str) -> Optional[Decimal]:
        """Parse a currency string to Decimal."""
        if not value_str:
            return None

        # Remove currency symbols and clean up
        cleaned = value_str.replace("$", "").replace(",", "").strip()
        if cleaned in ["-", "--", "", "N/A", "n/a", "not applicable"]:
            return None

        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    def _classify_security_type(self, name: str, symbol: Optional[str]) -> str:
        """Classify security type based on name and symbol."""
        name_lower = name.lower()

        if "money market" in name_lower or "cash" in name_lower:
            return "MONEY_MARKET"
        if "etf" in name_lower or "exchange traded" in name_lower:
            return "ETF"
        if "mutual fund" in name_lower or "fund" in name_lower:
            if "index" in name_lower or "etf" in name_lower:
                return "ETF"
            return "MUTUAL_FUND"
        if "bond" in name_lower or "treasury" in name_lower or "fixed income" in name_lower:
            return "BOND"
        if "gold" in name_lower or "silver" in name_lower or "commodity" in name_lower:
            return "ETF"  # Commodity ETFs

        return "STOCK"

    def _classify_asset_class(self, security_type: str, name: str) -> str:
        """Classify asset class based on security type and name."""
        name_lower = name.lower()

        if security_type in ["CASH", "MONEY_MARKET"]:
            return "CASH"
        if security_type == "BOND" or "bond" in name_lower or "treasury" in name_lower:
            return "FIXED_INCOME"
        if "gold" in name_lower or "silver" in name_lower or "commodity" in name_lower:
            return "ALTERNATIVE"
        if security_type in ["STOCK", "ETF", "MUTUAL_FUND"]:
            return "EQUITY"

        return "UNKNOWN"
