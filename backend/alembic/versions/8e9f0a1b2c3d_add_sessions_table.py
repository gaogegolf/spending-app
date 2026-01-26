"""Add sessions table for tracking user login sessions.

Revision ID: 8e9f0a1b2c3d
Revises: 7d8e9f0a1b2c
Create Date: 2026-01-26

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8e9f0a1b2c3d'
down_revision = '7d8e9f0a1b2c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create sessions table."""
    op.create_table(
        'sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('device_info', sa.String(255)),
        sa.Column('ip_address', sa.String(45)),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('last_activity', sa.DateTime, server_default=sa.func.now()),
        sa.Column('is_active', sa.Boolean, server_default='1'),
    )

    op.create_index('idx_sessions_user_id', 'sessions', ['user_id'])
    op.create_index('idx_sessions_token_hash', 'sessions', ['token_hash'])


def downgrade() -> None:
    """Drop sessions table."""
    op.drop_index('idx_sessions_token_hash', table_name='sessions')
    op.drop_index('idx_sessions_user_id', table_name='sessions')
    op.drop_table('sessions')
