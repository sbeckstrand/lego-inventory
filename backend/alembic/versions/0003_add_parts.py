"""add parts tables: part, set_part, loose_part

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "part",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("part_num", sa.String(length=32), nullable=False),
        sa.Column("color_id", sa.Integer(), nullable=True),
        sa.Column("color_name", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("img_url", sa.String(length=512), nullable=True),
        sa.UniqueConstraint("part_num", "color_name", name="uq_part_num_color"),
    )
    op.create_index("ix_part_part_num", "part", ["part_num"])

    op.create_table(
        "set_part",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("set_num", sa.String(length=32), nullable=False),
        sa.Column("part_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_spare", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["set_num"], ["catalog_set.set_num"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["part_id"], ["part.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_set_part_set_num", "set_part", ["set_num"])
    op.create_index("ix_set_part_part_id", "set_part", ["part_id"])

    op.create_table(
        "loose_part",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("part_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["part_id"], ["part.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("part_id", name="uq_loose_part_part_id"),
    )
    op.create_index("ix_loose_part_part_id", "loose_part", ["part_id"])


def downgrade() -> None:
    op.drop_table("loose_part")
    op.drop_table("set_part")
    op.drop_index("ix_part_part_num", table_name="part")
    op.drop_table("part")
