"""Initial schema with accounts, imports, transactions, and rules.

Revision ID: 001
Revises:
Create Date: 2026-01-08

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial database schema."""

    # Create accounts table
    op.create_table(
        'accounts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('institution', sa.String(255)),
        sa.Column('account_type', sa.Enum('CREDIT_CARD', 'CHECKING', 'SAVINGS', 'INVESTMENT', 'OTHER', name='accounttype'), nullable=False),
        sa.Column('account_number_last4', sa.String(4)),
        sa.Column('currency', sa.String(3), default='USD'),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )
    op.create_index('idx_accounts_user', 'accounts', ['user_id'])
    op.create_index('idx_accounts_type', 'accounts', ['account_type'])

    # Create import_records table
    op.create_table(
        'import_records',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(36), sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_type', sa.Enum('CSV', 'PDF', name='sourcetype'), nullable=False),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('file_size_bytes', sa.Integer),
        sa.Column('file_hash', sa.String(64)),
        sa.Column('status', sa.Enum('PENDING', 'PROCESSING', 'SUCCESS', 'FAILED', 'PARTIAL', name='importstatus'), nullable=False),
        sa.Column('error_message', sa.Text),
        sa.Column('transactions_imported', sa.Integer, default=0),
        sa.Column('transactions_duplicate', sa.Integer, default=0),
        sa.Column('import_metadata', sa.JSON),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('completed_at', sa.DateTime),
    )
    op.create_index('idx_imports_account', 'import_records', ['account_id'])
    op.create_index('idx_imports_status', 'import_records', ['status'])
    op.create_index('idx_imports_created', 'import_records', ['created_at'])

    # Create rules table
    op.create_table(
        'rules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('rule_type', sa.Enum('MERCHANT_MATCH', 'DESCRIPTION_REGEX', 'AMOUNT_RANGE', 'CATEGORY_OVERRIDE', 'COMPOSITE', name='ruletype'), nullable=False),
        sa.Column('pattern', sa.Text, nullable=False),
        sa.Column('action', sa.JSON, nullable=False),
        sa.Column('priority', sa.Integer, default=100),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('match_count', sa.Integer, default=0),
        sa.Column('name', sa.String(255)),
        sa.Column('description', sa.Text),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('last_matched_at', sa.DateTime),
    )
    op.create_index('idx_rules_user', 'rules', ['user_id'])
    op.create_index('idx_rules_type', 'rules', ['rule_type'])
    op.create_index('idx_rules_priority', 'rules', ['priority'])
    op.create_index('idx_rules_active', 'rules', ['is_active'])

    # Create transactions table
    op.create_table(
        'transactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(36), sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('import_id', sa.String(36), sa.ForeignKey('import_records.id', ondelete='SET NULL')),
        sa.Column('hash_dedup_key', sa.String(64), unique=True, nullable=False),
        sa.Column('date', sa.Date, nullable=False),
        sa.Column('post_date', sa.Date),
        sa.Column('description_raw', sa.Text, nullable=False),
        sa.Column('merchant_normalized', sa.String(255)),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('currency', sa.String(3), default='USD'),
        sa.Column('transaction_type', sa.Enum('EXPENSE', 'INCOME', 'TRANSFER', 'PAYMENT', 'REFUND', 'FEE_INTEREST', name='transactiontype'), nullable=False),
        sa.Column('category', sa.String(100)),
        sa.Column('subcategory', sa.String(100)),
        sa.Column('tags', sa.JSON, default=[]),
        sa.Column('is_spend', sa.Boolean, default=False, nullable=False),
        sa.Column('is_income', sa.Boolean, default=False, nullable=False),
        sa.Column('confidence', sa.Numeric(3, 2)),
        sa.Column('needs_review', sa.Boolean, default=False),
        sa.Column('reviewed_at', sa.DateTime),
        sa.Column('matched_rule_id', sa.String(36), sa.ForeignKey('rules.id', ondelete='SET NULL')),
        sa.Column('classification_method', sa.Enum('LLM', 'RULE', 'MANUAL', 'DEFAULT', name='classificationmethod')),
        sa.Column('user_note', sa.Text),
        sa.Column('transaction_metadata', sa.JSON),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )
    op.create_index('idx_transactions_account', 'transactions', ['account_id'])
    op.create_index('idx_transactions_date', 'transactions', ['date'])
    op.create_index('idx_transactions_type', 'transactions', ['transaction_type'])
    op.create_index('idx_transactions_is_spend', 'transactions', ['is_spend'])
    op.create_index('idx_transactions_category', 'transactions', ['category'])
    op.create_index('idx_transactions_merchant', 'transactions', ['merchant_normalized'])
    op.create_index('idx_transactions_needs_review', 'transactions', ['needs_review'])
    op.create_index('idx_transactions_hash', 'transactions', ['hash_dedup_key'])
    op.create_index('idx_transactions_account_date', 'transactions', ['account_id', 'date'])
    op.create_index('idx_transactions_spend_date', 'transactions', ['is_spend', 'date'])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table('transactions')
    op.drop_table('rules')
    op.drop_table('import_records')
    op.drop_table('accounts')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS accounttype')
    op.execute('DROP TYPE IF EXISTS sourcetype')
    op.execute('DROP TYPE IF EXISTS importstatus')
    op.execute('DROP TYPE IF EXISTS ruletype')
    op.execute('DROP TYPE IF EXISTS transactiontype')
    op.execute('DROP TYPE IF EXISTS classificationmethod')
