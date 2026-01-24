"""User model for authentication."""

from sqlalchemy import Column, String, DateTime, Boolean
from datetime import datetime
import uuid

from app.database import Base


class User(Base):
    """User model for authentication and multi-user support."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)

    # Account status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime)

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', username='{self.username}')>"
