"""Transaction model - core entity for financial transactions."""

from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum, JSON, Date, Numeric, Boolean, ARRAY
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.database import Base


class TransactionType(str, enum.Enum):
    """Types of financial transactions."""

    EXPENSE = "EXPENSE"  # Regular purchases - counts as spending
    INCOME = "INCOME"  # Salary, wages, bonuses - counts as income
    TRANSFER = "TRANSFER"  # Moving money between accounts - NOT spending or income
    UNCATEGORIZED = "UNCATEGORIZED"  # Transactions not yet categorized


class ClassificationMethod(str, enum.Enum):
    """How transaction was classified."""

    LLM = "LLM"  # Classified by LLM
    RULE = "RULE"  # Matched user rule
    MANUAL = "MANUAL"  # User manual edit
    DEFAULT = "DEFAULT"  # Default classification
    LEARNED = "LEARNED"  # Learned from user corrections


class Transaction(Base):
    """Transaction model - core entity for all financial transactions."""

    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    import_id = Column(String(36), ForeignKey("import_records.id", ondelete="SET NULL"))

    # Transaction identification and deduplication
    hash_dedup_key = Column(String(64), unique=True, nullable=False)  # SHA256 for dedup

    # Transaction details
    date = Column(Date, nullable=False, index=True)  # Transaction date
    post_date = Column(Date)  # Posting date (may differ from transaction date)
    description_raw = Column(Text, nullable=False)  # Original description from statement
    merchant_normalized = Column(String(255), index=True)  # Cleaned merchant name
    amount = Column(Numeric(15, 2), nullable=False)  # Always positive
    currency = Column(String(3), default="USD")

    # FX conversion fields (for multi-currency support)
    amount_usd = Column(Numeric(15, 2), nullable=True)  # USD-normalized amount
    fx_rate_used = Column(Numeric(18, 8), nullable=True)  # FX rate applied
    fx_rate_date = Column(Date, nullable=True)  # Date of the FX rate
    fx_rate_source = Column(String(50), nullable=True)  # "statement", "api", "none"

    # Classification (from LLM or rules)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    category = Column(String(100), index=True)  # e.g., "Food & Dining"
    subcategory = Column(String(100))  # e.g., "Restaurants"
    tags = Column(JSON, default=[])  # Array of tags (JSON for SQLite compatibility)

    # CRITICAL FLAGS for spending calculation
    is_spend = Column(Boolean, default=False, nullable=False, index=True)  # True only for actual expenses
    is_income = Column(Boolean, default=False, nullable=False, index=True)  # True for income

    # Confidence and review
    confidence = Column(Numeric(3, 2))  # 0.00 to 1.00 from LLM
    needs_review = Column(Boolean, default=False, index=True)
    reviewed_at = Column(DateTime)

    # Rule tracking
    matched_rule_id = Column(String(36), ForeignKey("rules.id", ondelete="SET NULL"))
    classification_method = Column(Enum(ClassificationMethod), default=ClassificationMethod.DEFAULT)

    # User notes
    user_note = Column(Text)

    # Metadata (store original CSV row, PDF data, etc.)
    transaction_metadata = Column(JSON)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    account = relationship("Account", back_populates="transactions")
    import_record = relationship("ImportRecord", back_populates="transactions")
    matched_rule = relationship("Rule", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction(id={self.id}, date={self.date}, merchant='{self.merchant_normalized}', amount={self.amount}, type={self.transaction_type})>"

    def set_is_spend_based_on_type(self):
        """Set is_spend flag based on transaction_type.

        CRITICAL: This enforces the business rule that:
        - EXPENSE counts as spending
        - INCOME counts as income
        - TRANSFER and UNCATEGORIZED do NOT count as spending or income
        """
        if self.transaction_type == TransactionType.EXPENSE:
            self.is_spend = True
            self.is_income = False
        elif self.transaction_type == TransactionType.INCOME:
            self.is_income = True
            self.is_spend = False
        else:  # TRANSFER, UNCATEGORIZED
            self.is_spend = False
            self.is_income = False
