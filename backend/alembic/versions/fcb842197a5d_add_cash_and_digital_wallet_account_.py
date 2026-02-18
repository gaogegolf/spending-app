"""add cash and digital wallet account types

Revision ID: fcb842197a5d
Revises: a0b1c2d3e4f5
Create Date: 2026-02-17 21:11:32.678946

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fcb842197a5d'
down_revision = 'a0b1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite doesn't enforce enum constraints, so no DDL needed.
    # The new values are valid at the application layer via the Python enum.
    pass

def downgrade() -> None:
    pass
