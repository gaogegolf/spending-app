"""Account model - represents credit cards and bank accounts."""

from sqlalchemy import Column, String, Boolean, DateTime, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.database import Base


class AccountType(str, enum.Enum):
    """Types of accounts."""

    CREDIT_CARD = "CREDIT_CARD"
    CHECKING = "CHECKING"
    SAVINGS = "SAVINGS"
    INVESTMENT = "INVESTMENT"
    OTHER = "OTHER"


class Account(Base):
    """Account model for credit cards and bank accounts."""

    __tablename__ = "accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, default="default_user")  # Simplified for MVP
    name = Column(String(255), nullable=False)
    institution = Column(String(255))
    account_type = Column(Enum(AccountType), nullable=False)
    account_number_last4 = Column(String(4))
    currency = Column(String(3), default="USD")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    imports = relationship("ImportRecord", back_populates="account", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="account", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Account(id={self.id}, name='{self.name}', type={self.account_type})>"
