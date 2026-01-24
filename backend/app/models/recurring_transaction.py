"""Recurring transaction model - for subscription/recurring payment detection."""

from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum, Numeric, Boolean, Date
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.database import Base


class RecurringFrequency(str, enum.Enum):
    """Frequency of recurring transactions."""

    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"


class RecurringTransaction(Base):
    """Model for detected or manually-created recurring transactions (subscriptions)."""

    __tablename__ = "recurring_transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, default="default_user")

    # Merchant identification
    merchant_normalized = Column(String(255), nullable=False, index=True)

    # Expected payment details
    expected_amount = Column(Numeric(15, 2), nullable=False)
    amount_tolerance = Column(Numeric(5, 2), default=5.0)  # Percentage tolerance (e.g., 5%)

    # Frequency and timing
    frequency = Column(Enum(RecurringFrequency), nullable=False)
    next_expected_date = Column(Date)
    last_transaction_id = Column(String(36), ForeignKey("transactions.id", ondelete="SET NULL"))

    # Status and detection
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_auto_detected = Column(Boolean, default=True, nullable=False)
    confidence = Column(Numeric(3, 2))  # 0.00 to 1.00, for auto-detected items

    # Classification
    category = Column(String(100))
    notes = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    last_transaction = relationship("Transaction", foreign_keys=[last_transaction_id])

    def __repr__(self):
        return f"<RecurringTransaction(id={self.id}, merchant='{self.merchant_normalized}', amount={self.expected_amount}, frequency={self.frequency})>"
