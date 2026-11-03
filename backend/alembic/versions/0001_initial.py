"""initial schema: catalog_set and owned_set

Revision ID: 0001
Revises:
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_set",
        sa.Column("set_num", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("num_parts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("image_url", sa.String(length=512), nullable=True),
        sa.Column("image_path", sa.String(length=512), nullable=True),
        sa.Column("parts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("minifigs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "owned_set",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("set_num", sa.String(length=32), nullable=False),
        sa.Column("purchased_date", sa.Date(), nullable=True),
        sa.Column("storage_location", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("condition", sa.String(length=32), nullable=False, server_default="New"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="In box"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["set_num"], ["catalog_set.set_num"]),
    )
    op.create_index("ix_owned_set_set_num", "owned_set", ["set_num"])


def downgrade() -> None:
    op.drop_index("ix_owned_set_set_num", table_name="owned_set")
    op.drop_table("owned_set")
    op.drop_table("catalog_set")
