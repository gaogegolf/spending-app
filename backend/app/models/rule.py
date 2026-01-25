"""Rule model - user-defined classification rules."""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Enum, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.database import Base


class RuleType(str, enum.Enum):
    """Types of rules for matching transactions."""

    MERCHANT_MATCH = "MERCHANT_MATCH"
    DESCRIPTION_REGEX = "DESCRIPTION_REGEX"
    AMOUNT_RANGE = "AMOUNT_RANGE"
    CATEGORY_OVERRIDE = "CATEGORY_OVERRIDE"
    COMPOSITE = "COMPOSITE"


class Rule(Base):
    """Rule model for user-defined transaction classification."""

    __tablename__ = "rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False)  # Required - no default to prevent data leakage
    rule_type = Column(Enum(RuleType), nullable=False)
    pattern = Column(Text, nullable=False)  # Pattern to match (merchant name, regex, JSON for complex)
    action = Column(JSON, nullable=False)  # Action to take: {transaction_type, category, subcategory, is_spend, etc.}
    priority = Column(Integer, default=100)  # Lower number = higher priority
    is_active = Column(Boolean, default=True)
    match_count = Column(Integer, default=0)  # Track how often rule is matched
    name = Column(String(255))  # User-friendly name
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_matched_at = Column(DateTime)

    # Relationships
    transactions = relationship("Transaction", back_populates="matched_rule")

    def __repr__(self):
        return f"<Rule(id={self.id}, name='{self.name}', type={self.rule_type}, priority={self.priority})>"
