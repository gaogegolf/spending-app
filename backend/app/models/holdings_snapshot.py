"""Holdings snapshot model - point-in-time snapshot of account holdings from a statement."""

from sqlalchemy import Column, String, Date, DateTime, Boolean, Numeric, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class HoldingsSnapshot(Base):
    """Point-in-time snapshot of account holdings from a brokerage statement."""

    __tablename__ = "holdings_snapshots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    import_id = Column(String(36), ForeignKey("import_records.id", ondelete="SET NULL"), nullable=True)

    # Statement info
    statement_date = Column(Date, nullable=False)  # End date of statement period
    statement_start_date = Column(Date)  # Start date (optional)

    # Totals from statement
    total_value = Column(Numeric(18, 2), nullable=False)  # Reported total account value
    total_cash = Column(Numeric(18, 2), default=0)  # Total cash/money market
    total_securities = Column(Numeric(18, 2), default=0)  # Total securities value

    # Validation / Reconciliation
    calculated_total = Column(Numeric(18, 2))  # Sum of positions (for reconciliation)
    is_reconciled = Column(Boolean, default=False)  # Does calculated ≈ reported?
    reconciliation_diff = Column(Numeric(18, 2))  # Difference amount

    # Multi-currency support
    base_currency = Column(String(3), default="USD")  # Account's base currency
    cash_balances = Column(JSON)  # Cash by currency: {"USD": 73438.91, "EUR": -59696.65}

    # Metadata
    currency = Column(String(3), default="USD")  # Legacy, use base_currency for new
    source_file_hash = Column(String(64))  # SHA256 for dedup
    raw_metadata = Column(JSON)  # Original extracted data for debugging
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    account = relationship("Account", back_populates="holdings_snapshots")
    import_record = relationship("ImportRecord", back_populates="holdings_snapshot")
    positions = relationship("Position", back_populates="snapshot", cascade="all, delete-orphan")
    fx_rates = relationship("FxRate", back_populates="snapshot", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<HoldingsSnapshot(id={self.id}, date={self.statement_date}, value={self.total_value})>"
