"""Import record model - tracks file import history."""

from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.database import Base


class SourceType(str, enum.Enum):
    """Types of import sources."""

    CSV = "CSV"
    PDF = "PDF"


class ImportStatus(str, enum.Enum):
    """Import processing status."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class ImportRecord(Base):
    """Import record model for tracking file imports."""

    __tablename__ = "import_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(Enum(SourceType), nullable=False)
    filename = Column(String(500), nullable=False)
    file_size_bytes = Column(Integer)
    file_hash = Column(String(64))  # SHA256 of file content for dedup
    status = Column(Enum(ImportStatus), default=ImportStatus.PENDING, nullable=False)
    error_message = Column(Text)
    transactions_imported = Column(Integer, default=0)
    transactions_duplicate = Column(Integer, default=0)
    import_metadata = Column(JSON)  # Store column mappings, parsing options, etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    # Relationships
    account = relationship("Account", back_populates="imports")
    transactions = relationship("Transaction", back_populates="import_record")

    def __repr__(self):
        return f"<ImportRecord(id={self.id}, filename='{self.filename}', status={self.status})>"
