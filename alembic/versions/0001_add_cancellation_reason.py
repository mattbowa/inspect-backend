"""add cancellation_reason to subscriptions

Revision ID: 0001
Revises:
Create Date: 2026-05-10

"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('subscriptions', sa.Column('cancellation_reason', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('subscriptions', 'cancellation_reason')
