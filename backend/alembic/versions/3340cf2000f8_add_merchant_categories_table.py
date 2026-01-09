"""add_merchant_categories_table

Revision ID: 3340cf2000f8
Revises: 001
Create Date: 2026-01-08 19:46:26.479093

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3340cf2000f8'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'merchant_categories',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False, default='default_user'),
        sa.Column('merchant_normalized', sa.String(255), nullable=False),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('confidence', sa.Float, nullable=False, default=1.0),
        sa.Column('source', sa.String(20), nullable=False, default='USER'),  # USER, AUTO, LLM
        sa.Column('times_applied', sa.Integer, nullable=False, default=0),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create unique index on user_id + merchant_normalized
    op.create_index(
        'idx_merchant_categories_user_merchant',
        'merchant_categories',
        ['user_id', 'merchant_normalized'],
        unique=True
    )

    # Create index on merchant for faster lookups
    op.create_index(
        'idx_merchant_categories_merchant',
        'merchant_categories',
        ['merchant_normalized']
    )


def downgrade() -> None:
    op.drop_index('idx_merchant_categories_merchant', 'merchant_categories')
    op.drop_index('idx_merchant_categories_user_merchant', 'merchant_categories')
    op.drop_table('merchant_categories')
