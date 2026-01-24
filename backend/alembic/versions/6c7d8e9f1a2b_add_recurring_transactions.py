"""Add recurring_transactions table for subscription detection.

Revision ID: 6c7d8e9f1a2b
Revises: 5b6c7d8e9f0a
Create Date: 2026-01-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6c7d8e9f1a2b'
down_revision = '5b6c7d8e9f0a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create recurring_transactions table."""

    op.create_table(
        'recurring_transactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False, server_default='default_user'),
        sa.Column('merchant_normalized', sa.String(255), nullable=False),
        sa.Column('expected_amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('amount_tolerance', sa.Numeric(5, 2), server_default='5.0'),
        sa.Column('frequency', sa.Enum('WEEKLY', 'BIWEEKLY', 'MONTHLY', 'QUARTERLY', 'YEARLY', name='recurringfrequency'), nullable=False),
        sa.Column('next_expected_date', sa.Date),
        sa.Column('last_transaction_id', sa.String(36), sa.ForeignKey('transactions.id', ondelete='SET NULL')),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='1'),
        sa.Column('is_auto_detected', sa.Boolean, nullable=False, server_default='1'),
        sa.Column('confidence', sa.Numeric(3, 2)),
        sa.Column('category', sa.String(100)),
        sa.Column('notes', sa.Text),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Indexes for common queries
    op.create_index('idx_recurring_user', 'recurring_transactions', ['user_id'])
    op.create_index('idx_recurring_merchant', 'recurring_transactions', ['merchant_normalized'])
    op.create_index('idx_recurring_active', 'recurring_transactions', ['is_active'])
    op.create_index('idx_recurring_next_date', 'recurring_transactions', ['next_expected_date'])
    op.create_index('idx_recurring_user_active', 'recurring_transactions', ['user_id', 'is_active'])


def downgrade() -> None:
    """Drop recurring_transactions table."""

    op.drop_table('recurring_transactions')
    op.execute('DROP TYPE IF EXISTS recurringfrequency')
