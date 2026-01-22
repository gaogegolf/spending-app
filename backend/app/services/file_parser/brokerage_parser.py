"""Base brokerage statement parser with provider detection."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import pdfplumber


@dataclass
class PositionData:
    """Data for a single position/holding."""

    symbol: Optional[str]
    cusip: Optional[str]
    security_name: str
    security_type: str  # STOCK, ETF, MUTUAL_FUND, BOND, CASH, MONEY_MARKET, RSU, ESPP, OPTION, OTHER
    quantity: Optional[Decimal]
    price: Optional[Decimal]
    market_value: Decimal
    cost_basis: Optional[Decimal]
    asset_class: str  # EQUITY, FIXED_INCOME, CASH, ALTERNATIVE, UNKNOWN
    is_vested: bool = True
    vesting_date: Optional[date] = None
    row_index: int = 0


@dataclass
class BrokerageParseResult:
    """Result of parsing a brokerage statement."""

    success: bool
    provider: str  # "fidelity", "schwab", "ibkr", "vanguard", "equatex"
    account_type: str  # BROKERAGE, IRA_ROTH, IRA_TRADITIONAL, RETIREMENT_401K, STOCK_PLAN
    account_identifier: str  # Masked account number

    # Statement dates
    statement_date: Optional[date]
    statement_start_date: Optional[date]

    # Totals from statement
    total_value: Decimal
    total_cash: Decimal
    total_securities: Decimal

    # Holdings
    positions: List[PositionData]

    # Validation
    calculated_total: Decimal
    is_reconciled: bool
    reconciliation_diff: Decimal

    # Messages
    errors: List[str]
    warnings: List[str]

    # Raw data for debugging
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


def detect_brokerage_provider(text: str) -> Optional[str]:
    """Detect brokerage provider from statement text.

    Args:
        text: Full text extracted from the PDF

    Returns:
        Provider string ("fidelity", "schwab", etc.) or None if not detected
    """
    text_lower = text.lower()

    # Fidelity indicators
    fidelity_indicators = [
        "fidelity investments",
        "fidelity brokerage",
        "national financial services",
        "fidelity management",
        "fmr llc",
    ]
    if any(ind in text_lower for ind in fidelity_indicators):
        return "fidelity"

    # Schwab indicators
    schwab_indicators = [
        "charles schwab",
        "schwab one",
        "schwab & co",
        "schwab.com",
    ]
    if any(ind in text_lower for ind in schwab_indicators):
        return "schwab"

    # Interactive Brokers indicators
    ibkr_indicators = [
        "interactive brokers",
        "ibkr",
        "interactivebrokers",
    ]
    if any(ind in text_lower for ind in ibkr_indicators):
        return "ibkr"

    # Vanguard indicators
    vanguard_indicators = [
        "vanguard",
        "the vanguard group",
    ]
    if any(ind in text_lower for ind in vanguard_indicators):
        return "vanguard"

    # Equatex / Stock plan indicators
    equatex_indicators = [
        "equatex",
        "employee stock plan",
        "participant plan holdings",
    ]
    if any(ind in text_lower for ind in equatex_indicators):
        return "equatex"

    return None


def detect_account_type(text: str, provider: str) -> str:
    """Detect account type from statement text.

    Args:
        text: Full text extracted from the PDF
        provider: Detected provider

    Returns:
        Account type string (BROKERAGE, IRA_ROTH, etc.)
    """
    text_lower = text.lower()

    # Roth IRA indicators
    if "roth ira" in text_lower or "roth individual" in text_lower:
        return "IRA_ROTH"

    # Traditional IRA indicators
    if ("traditional ira" in text_lower or "rollover ira" in text_lower or
            ("ira" in text_lower and "roth" not in text_lower)):
        return "IRA_TRADITIONAL"

    # 401(k) indicators
    if "401(k)" in text_lower or "401k" in text_lower or "retirement plan" in text_lower:
        return "RETIREMENT_401K"

    # Stock plan indicators
    if provider == "equatex" or "stock plan" in text_lower or "rsu" in text_lower or "espp" in text_lower:
        return "STOCK_PLAN"

    # Joint/Individual brokerage (default for taxable)
    if "joint" in text_lower or "individual" in text_lower or "brokerage" in text_lower:
        return "BROKERAGE"

    return "BROKERAGE"  # Default


class BaseBrokerageParser(ABC):
    """Abstract base class for brokerage statement parsers."""

    def __init__(self, file_path: str):
        """Initialize parser.

        Args:
            file_path: Path to PDF file
        """
        self.file_path = file_path
        self.pdf = None
        self.full_text = ""
        self.provider: Optional[str] = None
        self.account_type: Optional[str] = None

    def _open_pdf(self) -> None:
        """Open PDF and extract full text for detection."""
        self.pdf = pdfplumber.open(self.file_path)
        text_parts = []
        for page in self.pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
        self.full_text = "\n".join(text_parts)

    def _close_pdf(self) -> None:
        """Close PDF file."""
        if self.pdf:
            self.pdf.close()
            self.pdf = None

    def detect_provider(self) -> Optional[str]:
        """Detect brokerage provider from PDF.

        Returns:
            Provider string or None if not detected
        """
        if not self.full_text:
            self._open_pdf()
        self.provider = detect_brokerage_provider(self.full_text)
        return self.provider

    def detect_account_type(self) -> str:
        """Detect account type from PDF.

        Returns:
            Account type string
        """
        if not self.full_text:
            self._open_pdf()
        if not self.provider:
            self.detect_provider()
        self.account_type = detect_account_type(self.full_text, self.provider or "")
        return self.account_type

    @abstractmethod
    def parse(self) -> BrokerageParseResult:
        """Parse statement and return holdings snapshot.

        Returns:
            BrokerageParseResult with positions and totals
        """
        pass

    @abstractmethod
    def _extract_account_identifier(self) -> str:
        """Extract masked account identifier from statement.

        Returns:
            Account identifier string (e.g., "****1234")
        """
        pass

    @abstractmethod
    def _extract_statement_dates(self) -> tuple[Optional[date], Optional[date]]:
        """Extract statement date(s) from PDF.

        Returns:
            Tuple of (statement_date, statement_start_date)
        """
        pass

    @abstractmethod
    def _extract_totals(self) -> tuple[Decimal, Decimal, Decimal]:
        """Extract total values from statement.

        Returns:
            Tuple of (total_value, total_cash, total_securities)
        """
        pass

    @abstractmethod
    def _extract_positions(self) -> List[PositionData]:
        """Extract position/holdings data from statement.

        Returns:
            List of PositionData objects
        """
        pass

    def _calculate_total(self, positions: List[PositionData]) -> Decimal:
        """Calculate total from positions for reconciliation.

        Args:
            positions: List of extracted positions

        Returns:
            Sum of all position market values
        """
        return sum(p.market_value for p in positions)

    def _reconcile(
        self,
        reported_total: Decimal,
        calculated_total: Decimal,
        tolerance: Decimal = Decimal("0.01")
    ) -> tuple[bool, Decimal]:
        """Check if calculated total matches reported total.

        Args:
            reported_total: Total value from statement
            calculated_total: Sum of extracted positions
            tolerance: Acceptable difference ratio (default 1%)

        Returns:
            Tuple of (is_reconciled, difference)
        """
        diff = abs(reported_total - calculated_total)
        if reported_total == 0:
            is_reconciled = calculated_total == 0
        else:
            ratio = diff / reported_total
            is_reconciled = ratio <= tolerance
        return is_reconciled, diff
