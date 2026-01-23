"""FxRate model - FX rates from brokerage statements for multi-currency support."""

from sqlalchemy import Column, String, Date, Numeric, ForeignKey
from sqlalchemy.orm import relationship
import uuid

from app.database import Base


class FxRate(Base):
    """FX rate extracted from a brokerage statement for currency conversion."""

    __tablename__ = "fx_rates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    snapshot_id = Column(String(36), ForeignKey("holdings_snapshots.id", ondelete="CASCADE"), nullable=False)

    # Currency pair
    from_currency = Column(String(3), nullable=False)  # e.g., "EUR"
    to_currency = Column(String(3), default="USD")  # Base currency, usually "USD"

    # Rate info
    rate = Column(Numeric(18, 8), nullable=False)  # e.g., 1.17460000 for EUR/USD
    rate_date = Column(Date, nullable=False)  # Date the rate applies to

    # Source tracking
    source = Column(String(50), default="statement")  # "statement", "api", etc.

    # Relationships
    snapshot = relationship("HoldingsSnapshot", back_populates="fx_rates")

    def __repr__(self):
        return f"<FxRate({self.from_currency}/{self.to_currency}={self.rate}, date={self.rate_date})>"
