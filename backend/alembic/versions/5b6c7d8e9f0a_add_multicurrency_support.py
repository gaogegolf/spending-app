"""add multi-currency support: fx_rates table and related columns

Revision ID: 5b6c7d8e9f0a
Revises: 4a5b6c7d8e9f
Create Date: 2026-01-22 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5b6c7d8e9f0a'
down_revision = '4a5b6c7d8e9f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create fx_rates table
    op.create_table(
        'fx_rates',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('snapshot_id', sa.String(36), sa.ForeignKey('holdings_snapshots.id', ondelete='CASCADE'), nullable=False),
        sa.Column('from_currency', sa.String(3), nullable=False),
        sa.Column('to_currency', sa.String(3), default='USD'),
        sa.Column('rate', sa.Numeric(18, 8), nullable=False),
        sa.Column('rate_date', sa.Date, nullable=False),
        sa.Column('source', sa.String(50), default='statement'),
    )

    # Create index on snapshot_id for faster lookups
    op.create_index('idx_fx_rates_snapshot', 'fx_rates', ['snapshot_id'])

    # Add multi-currency columns to positions table
    op.add_column('positions', sa.Column('market_value_usd', sa.Numeric(18, 2), nullable=True))
    op.add_column('positions', sa.Column('fx_rate_used', sa.Numeric(18, 8), nullable=True))

    # Backfill market_value_usd with market_value for existing USD positions
    op.execute("UPDATE positions SET market_value_usd = market_value WHERE currency = 'USD' OR currency IS NULL")

    # Add multi-currency columns to holdings_snapshots table
    op.add_column('holdings_snapshots', sa.Column('base_currency', sa.String(3), nullable=True, server_default='USD'))
    op.add_column('holdings_snapshots', sa.Column('cash_balances', sa.JSON, nullable=True))


def downgrade() -> None:
    # Remove columns from holdings_snapshots
    op.drop_column('holdings_snapshots', 'cash_balances')
    op.drop_column('holdings_snapshots', 'base_currency')

    # Remove columns from positions
    op.drop_column('positions', 'fx_rate_used')
    op.drop_column('positions', 'market_value_usd')

    # Drop fx_rates table
    op.drop_index('idx_fx_rates_snapshot', 'fx_rates')
    op.drop_table('fx_rates')
