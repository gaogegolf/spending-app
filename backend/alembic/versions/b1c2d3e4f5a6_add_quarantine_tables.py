"""Add quarantine tables.

Adds quarantined_transactions table and quarantine columns to import_records.

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-01-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = 'a0b1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create quarantined_transactions table and add quarantine columns to import_records."""
    # Create quarantined_transactions table
    op.execute("""
        CREATE TABLE quarantined_transactions (
            id VARCHAR(36) PRIMARY KEY,
            import_id VARCHAR(36) NOT NULL REFERENCES import_records(id) ON DELETE CASCADE,
            account_id VARCHAR(36) REFERENCES accounts(id) ON DELETE SET NULL,
            user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            raw_data JSON NOT NULL,
            error_type VARCHAR(20) NOT NULL,
            error_message TEXT NOT NULL,
            error_field VARCHAR(100),
            retry_count INTEGER DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME
        )
    """)

    op.execute("CREATE INDEX idx_quarantined_transactions_import_id ON quarantined_transactions(import_id)")
    op.execute("CREATE INDEX idx_quarantined_transactions_status ON quarantined_transactions(status)")
    op.execute("CREATE INDEX idx_quarantined_transactions_user_id ON quarantined_transactions(user_id)")

    # Add columns to import_records (SQLite requires table recreation)
    op.execute("""
        CREATE TABLE import_records_new (
            id VARCHAR(36) PRIMARY KEY,
            account_id VARCHAR(36) REFERENCES accounts(id) ON DELETE CASCADE,
            user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
            source_type VARCHAR(10) NOT NULL,
            filename VARCHAR(500) NOT NULL,
            file_size_bytes INTEGER,
            file_hash VARCHAR(64),
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            error_message TEXT,
            transactions_imported INTEGER DEFAULT 0,
            transactions_duplicate INTEGER DEFAULT 0,
            transactions_quarantined INTEGER DEFAULT 0,
            quarantine_resolved BOOLEAN DEFAULT 1,
            import_metadata JSON,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME
        )
    """)

    op.execute("""
        INSERT INTO import_records_new (
            id, account_id, user_id, source_type, filename, file_size_bytes, file_hash,
            status, error_message, transactions_imported, transactions_duplicate,
            transactions_quarantined, quarantine_resolved, import_metadata, created_at, completed_at
        )
        SELECT
            id, account_id, user_id, source_type, filename, file_size_bytes, file_hash,
            status, error_message, transactions_imported, transactions_duplicate,
            0, 1, import_metadata, created_at, completed_at
        FROM import_records
    """)

    op.execute("DROP TABLE import_records")
    op.execute("ALTER TABLE import_records_new RENAME TO import_records")

    # Recreate indexes
    op.execute("CREATE INDEX idx_import_records_account_id ON import_records(account_id)")
    op.execute("CREATE INDEX idx_import_records_user_id ON import_records(user_id)")


def downgrade() -> None:
    """Remove quarantine tables and columns, restoring import_records to previous state."""
    op.execute("DROP TABLE IF EXISTS quarantined_transactions")

    op.execute("""
        CREATE TABLE import_records_new (
            id VARCHAR(36) PRIMARY KEY,
            account_id VARCHAR(36) REFERENCES accounts(id) ON DELETE CASCADE,
            user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
            source_type VARCHAR(10) NOT NULL,
            filename VARCHAR(500) NOT NULL,
            file_size_bytes INTEGER,
            file_hash VARCHAR(64),
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            error_message TEXT,
            transactions_imported INTEGER DEFAULT 0,
            transactions_duplicate INTEGER DEFAULT 0,
            import_metadata JSON,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME
        )
    """)

    op.execute("""
        INSERT INTO import_records_new
        SELECT id, account_id, user_id, source_type, filename, file_size_bytes, file_hash,
               status, error_message, transactions_imported, transactions_duplicate,
               import_metadata, created_at, completed_at
        FROM import_records
    """)

    op.execute("DROP TABLE import_records")
    op.execute("ALTER TABLE import_records_new RENAME TO import_records")

    # Recreate index from previous migration (a0b1c2d3e4f5)
    op.execute("CREATE INDEX idx_import_records_user_id ON import_records(user_id)")
