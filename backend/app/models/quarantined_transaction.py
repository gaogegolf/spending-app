"""Quarantined transaction model - stores failed import rows for review."""

from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.database import Base


class QuarantineErrorType(str, enum.Enum):
    """Types of quarantine errors."""
    PARSE_ERROR = "PARSE_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DUPLICATE = "DUPLICATE"


class QuarantineStatus(str, enum.Enum):
    """Quarantine item status."""
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    DISCARDED = "DISCARDED"


class QuarantinedTransaction(Base):
    """Quarantined transaction model for failed import rows."""

    __tablename__ = "quarantined_transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    import_id = Column(String(36), ForeignKey("import_records.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(String(36), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Original data
    raw_data = Column(JSON, nullable=False)

    # Error details
    error_type = Column(Enum(QuarantineErrorType), nullable=False)
    error_message = Column(Text, nullable=False)
    error_field = Column(String(100), nullable=True)

    # Status tracking
    retry_count = Column(Integer, default=0)
    status = Column(Enum(QuarantineStatus), default=QuarantineStatus.PENDING, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    # Relationships
    import_record = relationship("ImportRecord", back_populates="quarantined_transactions")
    account = relationship("Account")
    user = relationship("User")

    def __repr__(self):
        return f"<QuarantinedTransaction(id={self.id}, error_type={self.error_type}, status={self.status})>"
