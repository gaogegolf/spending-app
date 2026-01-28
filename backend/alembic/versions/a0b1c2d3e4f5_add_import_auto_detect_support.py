"""Add auto-detect support for import_records.

Makes account_id nullable and adds user_id for pending imports.

Revision ID: a0b1c2d3e4f5
Revises: 9f0a1b2c3d4e
Create Date: 2026-01-26

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a0b1c2d3e4f5'
down_revision = '9f0a1b2c3d4e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Make account_id nullable and add user_id column."""
    # SQLite doesn't support ALTER COLUMN, so we need to recreate the table
    # Create new import_records table with nullable account_id and user_id
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

    # Copy data from old table
    op.execute("""
        INSERT INTO import_records_new (
            id, account_id, source_type, filename, file_size_bytes, file_hash,
            status, error_message, transactions_imported, transactions_duplicate,
            import_metadata, created_at, completed_at
        )
        SELECT
            id, account_id, source_type, filename, file_size_bytes, file_hash,
            status, error_message, transactions_imported, transactions_duplicate,
            import_metadata, created_at, completed_at
        FROM import_records
    """)

    # Drop old table and rename new one
    op.execute("DROP TABLE import_records")
    op.execute("ALTER TABLE import_records_new RENAME TO import_records")

    # Create index for user_id
    op.create_index('idx_import_records_user_id', 'import_records', ['user_id'])


def downgrade() -> None:
    """Revert to non-nullable account_id and remove user_id."""
    # Drop the user_id index
    op.drop_index('idx_import_records_user_id', table_name='import_records')

    # Recreate original table structure (account_id NOT NULL, no user_id)
    op.execute("""
        CREATE TABLE import_records_old (
            id VARCHAR(36) PRIMARY KEY,
            account_id VARCHAR(36) NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
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

    # Copy data back (only records with account_id)
    op.execute("""
        INSERT INTO import_records_old
        SELECT
            id, account_id, source_type, filename, file_size_bytes, file_hash,
            status, error_message, transactions_imported, transactions_duplicate,
            import_metadata, created_at, completed_at
        FROM import_records
        WHERE account_id IS NOT NULL
    """)

    # Drop and rename
    op.execute("DROP TABLE import_records")
    op.execute("ALTER TABLE import_records_old RENAME TO import_records")
