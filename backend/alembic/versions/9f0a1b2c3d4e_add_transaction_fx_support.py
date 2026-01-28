"""Add FX rate fields to transactions table for currency conversion support.

Revision ID: 9f0a1b2c3d4e
Revises: 8e9f0a1b2c3d
Create Date: 2026-01-26

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9f0a1b2c3d4e'
down_revision = '8e9f0a1b2c3d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add FX conversion fields to transactions and make fx_rates.snapshot_id nullable."""
    # Add FX fields to transactions table
    op.add_column('transactions', sa.Column('amount_usd', sa.Numeric(15, 2), nullable=True))
    op.add_column('transactions', sa.Column('fx_rate_used', sa.Numeric(18, 8), nullable=True))
    op.add_column('transactions', sa.Column('fx_rate_date', sa.Date, nullable=True))
    op.add_column('transactions', sa.Column('fx_rate_source', sa.String(50), nullable=True))

    # Backfill amount_usd for existing USD transactions
    op.execute("UPDATE transactions SET amount_usd = amount WHERE currency = 'USD' OR currency IS NULL")
    op.execute("UPDATE transactions SET fx_rate_source = 'none' WHERE currency = 'USD' OR currency IS NULL")

    # Make fx_rates.snapshot_id nullable (for standalone API-fetched rates)
    # SQLite doesn't support ALTER COLUMN, so we need to recreate the table
    # For SQLite compatibility, we'll create a new table, copy data, drop old, rename
    op.execute("""
        CREATE TABLE fx_rates_new (
            id VARCHAR(36) PRIMARY KEY,
            snapshot_id VARCHAR(36) REFERENCES holdings_snapshots(id) ON DELETE CASCADE,
            from_currency VARCHAR(3) NOT NULL,
            to_currency VARCHAR(3) DEFAULT 'USD',
            rate NUMERIC(18, 8) NOT NULL,
            rate_date DATE NOT NULL,
            source VARCHAR(50) DEFAULT 'statement'
        )
    """)
    op.execute("INSERT INTO fx_rates_new SELECT * FROM fx_rates")
    op.execute("DROP TABLE fx_rates")
    op.execute("ALTER TABLE fx_rates_new RENAME TO fx_rates")

    # Create index for currency pair lookups
    op.create_index('idx_fx_rates_currency_date', 'fx_rates', ['from_currency', 'to_currency', 'rate_date'])


def downgrade() -> None:
    """Remove FX fields from transactions and revert fx_rates changes."""
    # Drop the currency lookup index
    op.drop_index('idx_fx_rates_currency_date', table_name='fx_rates')

    # Restore fx_rates with non-nullable snapshot_id
    op.execute("""
        CREATE TABLE fx_rates_old (
            id VARCHAR(36) PRIMARY KEY,
            snapshot_id VARCHAR(36) NOT NULL REFERENCES holdings_snapshots(id) ON DELETE CASCADE,
            from_currency VARCHAR(3) NOT NULL,
            to_currency VARCHAR(3) DEFAULT 'USD',
            rate NUMERIC(18, 8) NOT NULL,
            rate_date DATE NOT NULL,
            source VARCHAR(50) DEFAULT 'statement'
        )
    """)
    op.execute("INSERT INTO fx_rates_old SELECT * FROM fx_rates WHERE snapshot_id IS NOT NULL")
    op.execute("DROP TABLE fx_rates")
    op.execute("ALTER TABLE fx_rates_old RENAME TO fx_rates")

    # Remove FX columns from transactions
    op.drop_column('transactions', 'fx_rate_source')
    op.drop_column('transactions', 'fx_rate_date')
    op.drop_column('transactions', 'fx_rate_used')
    op.drop_column('transactions', 'amount_usd')
