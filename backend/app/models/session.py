"""Session model for tracking user login sessions."""

from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.database import Base


class Session(Base):
    """Session model for tracking user login sessions.

    Stores session information to allow users to view and revoke active sessions.
    """

    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(64), nullable=False)  # SHA256 hash of refresh token
    device_info = Column(String(255))  # User agent string
    ip_address = Column(String(45))  # IPv4 or IPv6 address
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Indexes for efficient lookups
    __table_args__ = (
        Index('idx_sessions_user_id', 'user_id'),
        Index('idx_sessions_token_hash', 'token_hash'),
    )

    # Relationship to user
    user = relationship("User", backref="sessions")

    def __repr__(self):
        return f"<Session(id={self.id}, user_id={self.user_id}, active={self.is_active})>"
