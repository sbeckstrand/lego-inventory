"""add theme tracking to catalog_set

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("catalog_set", sa.Column("theme_id", sa.Integer(), nullable=True))
    op.add_column("catalog_set", sa.Column("theme", sa.String(length=128), nullable=True))
    op.create_index("ix_catalog_set_theme", "catalog_set", ["theme"])


def downgrade() -> None:
    op.drop_index("ix_catalog_set_theme", table_name="catalog_set")
    op.drop_column("catalog_set", "theme")
    op.drop_column("catalog_set", "theme_id")
