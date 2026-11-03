"""add minifig tables: minifig, set_minifig

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "minifig",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fig_num", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("img_url", sa.String(length=512), nullable=True),
        sa.UniqueConstraint("fig_num", name="uq_minifig_fig_num"),
    )
    op.create_index("ix_minifig_fig_num", "minifig", ["fig_num"])

    op.create_table(
        "set_minifig",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("set_num", sa.String(length=32), nullable=False),
        sa.Column("minifig_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["set_num"], ["catalog_set.set_num"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["minifig_id"], ["minifig.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_set_minifig_set_num", "set_minifig", ["set_num"])
    op.create_index("ix_set_minifig_minifig_id", "set_minifig", ["minifig_id"])


def downgrade() -> None:
    op.drop_table("set_minifig")
    op.drop_index("ix_minifig_fig_num", table_name="minifig")
    op.drop_table("minifig")
