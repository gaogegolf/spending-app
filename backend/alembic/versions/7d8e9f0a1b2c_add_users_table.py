"""Add users table for authentication.

Revision ID: 7d8e9f0a1b2c
Revises: 5b6c7d8e9f0a
Create Date: 2026-01-23

"""
from alembic import op
import sqlalchemy as sa
import uuid


# revision identifiers, used by Alembic.
revision = '7d8e9f0a1b2c'
down_revision = '5b6c7d8e9f0a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create users table and migrate existing data."""

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('username', sa.String(100), unique=True, nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='1'),
        sa.Column('is_verified', sa.Boolean, nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('last_login_at', sa.DateTime),
    )

    # Create indexes
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_username', 'users', ['username'])

    # Insert default user for existing data migration
    # Using a placeholder password hash (users should reset password)
    # This is bcrypt hash for "changeme123"
    default_password_hash = "$2b$12$DKd1/SPB6SMxgVCTHP2oeOGJ40I9sFUV1hqMqxusOX0owuxI7cbkK"

    op.execute(f"""
        INSERT INTO users (id, email, username, hashed_password, is_active, is_verified)
        VALUES ('default_user', 'default@example.com', 'default_user', '{default_password_hash}', 1, 1)
    """)


def downgrade() -> None:
    """Drop users table."""

    op.drop_table('users')
