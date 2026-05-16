"""add email to scans

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-16

"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('scans', sa.Column('email', sa.String(), nullable=True))
    op.create_index('ix_scans_email', 'scans', ['email'])


def downgrade() -> None:
    op.drop_index('ix_scans_email', 'scans')
    op.drop_column('scans', 'email')
