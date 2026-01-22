"""add holdings_snapshots and positions tables

Revision ID: 4a5b6c7d8e9f
Revises: 3340cf2000f8
Create Date: 2026-01-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4a5b6c7d8e9f'
down_revision = '3340cf2000f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create holdings_snapshots table
    op.create_table(
        'holdings_snapshots',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(36), sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('import_id', sa.String(36), sa.ForeignKey('import_records.id', ondelete='SET NULL'), nullable=True),
        sa.Column('statement_date', sa.Date, nullable=False),
        sa.Column('statement_start_date', sa.Date, nullable=True),
        sa.Column('total_value', sa.Numeric(18, 2), nullable=False),
        sa.Column('total_cash', sa.Numeric(18, 2), nullable=True, default=0),
        sa.Column('total_securities', sa.Numeric(18, 2), nullable=True, default=0),
        sa.Column('calculated_total', sa.Numeric(18, 2), nullable=True),
        sa.Column('is_reconciled', sa.Boolean, default=False),
        sa.Column('reconciliation_diff', sa.Numeric(18, 2), nullable=True),
        sa.Column('currency', sa.String(3), default='USD'),
        sa.Column('source_file_hash', sa.String(64), nullable=True),
        sa.Column('raw_metadata', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create index on account_id for faster lookups
    op.create_index('idx_holdings_snapshots_account', 'holdings_snapshots', ['account_id'])

    # Create index on statement_date for time-series queries
    op.create_index('idx_holdings_snapshots_date', 'holdings_snapshots', ['statement_date'])

    # Create positions table
    op.create_table(
        'positions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('snapshot_id', sa.String(36), sa.ForeignKey('holdings_snapshots.id', ondelete='CASCADE'), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=True),
        sa.Column('cusip', sa.String(9), nullable=True),
        sa.Column('security_name', sa.String(500), nullable=False),
        sa.Column('security_type', sa.String(20), default='OTHER'),  # STOCK, ETF, MUTUAL_FUND, BOND, CASH, MONEY_MARKET, RSU, ESPP, OPTION, OTHER
        sa.Column('quantity', sa.Numeric(18, 6), nullable=True),
        sa.Column('price', sa.Numeric(18, 4), nullable=True),
        sa.Column('market_value', sa.Numeric(18, 2), nullable=False),
        sa.Column('cost_basis', sa.Numeric(18, 2), nullable=True),
        sa.Column('is_vested', sa.Boolean, default=True),
        sa.Column('vesting_date', sa.Date, nullable=True),
        sa.Column('asset_class', sa.String(20), default='UNKNOWN'),  # EQUITY, FIXED_INCOME, CASH, ALTERNATIVE, UNKNOWN
        sa.Column('currency', sa.String(3), default='USD'),
        sa.Column('row_index', sa.Integer, nullable=True),
    )

    # Create index on snapshot_id for faster lookups
    op.create_index('idx_positions_snapshot', 'positions', ['snapshot_id'])

    # Create index on symbol for filtering by security
    op.create_index('idx_positions_symbol', 'positions', ['symbol'])


def downgrade() -> None:
    op.drop_index('idx_positions_symbol', 'positions')
    op.drop_index('idx_positions_snapshot', 'positions')
    op.drop_table('positions')
    op.drop_index('idx_holdings_snapshots_date', 'holdings_snapshots')
    op.drop_index('idx_holdings_snapshots_account', 'holdings_snapshots')
    op.drop_table('holdings_snapshots')
