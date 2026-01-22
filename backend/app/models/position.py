"""Position model - individual holding/position within a holdings snapshot."""

from sqlalchemy import Column, String, Date, Boolean, Numeric, Integer, ForeignKey, Enum
from sqlalchemy.orm import relationship
import uuid
import enum

from app.database import Base


class PositionType(str, enum.Enum):
    """Types of investment positions."""

    STOCK = "STOCK"
    ETF = "ETF"
    MUTUAL_FUND = "MUTUAL_FUND"
    BOND = "BOND"
    CASH = "CASH"
    MONEY_MARKET = "MONEY_MARKET"
    RSU = "RSU"
    ESPP = "ESPP"
    OPTION = "OPTION"
    OTHER = "OTHER"


class AssetClass(str, enum.Enum):
    """Asset classification for portfolio analysis."""

    EQUITY = "EQUITY"
    FIXED_INCOME = "FIXED_INCOME"
    CASH = "CASH"
    ALTERNATIVE = "ALTERNATIVE"
    UNKNOWN = "UNKNOWN"


class Position(Base):
    """Individual holding/position within a snapshot."""

    __tablename__ = "positions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    snapshot_id = Column(String(36), ForeignKey("holdings_snapshots.id", ondelete="CASCADE"), nullable=False)

    # Security identification
    symbol = Column(String(20))  # Ticker (e.g., "VOO", "META")
    cusip = Column(String(9))  # CUSIP if available
    security_name = Column(String(500), nullable=False)  # Full name
    security_type = Column(Enum(PositionType), default=PositionType.OTHER)

    # Holdings
    quantity = Column(Numeric(18, 6))  # Shares/units (supports fractional)
    price = Column(Numeric(18, 4))  # Price per share (if available)
    market_value = Column(Numeric(18, 2), nullable=False)  # Total market value
    cost_basis = Column(Numeric(18, 2))  # Cost basis (if available)

    # For RSU/stock plans
    is_vested = Column(Boolean, default=True)  # False for locked/unvested
    vesting_date = Column(Date)  # When it vests (if unvested)

    # Classification
    asset_class = Column(Enum(AssetClass), default=AssetClass.UNKNOWN)

    # Metadata
    currency = Column(String(3), default="USD")
    row_index = Column(Integer)  # Original row index for deduplication

    # Relationships
    snapshot = relationship("HoldingsSnapshot", back_populates="positions")

    def __repr__(self):
        return f"<Position(symbol={self.symbol}, name='{self.security_name[:30]}...', value={self.market_value})>"
