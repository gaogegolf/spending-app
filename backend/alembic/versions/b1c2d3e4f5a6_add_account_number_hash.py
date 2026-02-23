"""add account_number_hash column

Revision ID: b1c2d3e4f5a6
Revises: fcb842197a5d
Create Date: 2026-02-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = 'fcb842197a5d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('account_number_hash', sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column('accounts', 'account_number_hash')
