"""Merchant Category model for learning merchant categorizations."""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, Index
from app.database import Base


class MerchantCategory(Base):
    """Learned merchant category mappings.

    This table stores user-learned categorizations for merchants.
    When a user manually categorizes a transaction, we save the merchant → category mapping.
    Future transactions from the same merchant will auto-apply this category.
    """

    __tablename__ = "merchant_categories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, default="default_user")
    merchant_normalized = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    confidence = Column(Float, nullable=False, default=1.0)
    source = Column(String(20), nullable=False, default="USER")  # USER, AUTO, LLM
    times_applied = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_merchant_categories_user_merchant', 'user_id', 'merchant_normalized', unique=True),
        Index('idx_merchant_categories_merchant', 'merchant_normalized'),
    )

    def __repr__(self):
        return f"<MerchantCategory(merchant='{self.merchant_normalized}', category='{self.category}', confidence={self.confidence})>"
