"""add loose_minifig table

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "loose_minifig",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("minifig_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["minifig_id"], ["minifig.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("minifig_id", name="uq_loose_minifig_minifig_id"),
    )
    op.create_index("ix_loose_minifig_minifig_id", "loose_minifig", ["minifig_id"])


def downgrade() -> None:
    op.drop_index("ix_loose_minifig_minifig_id", table_name="loose_minifig")
    op.drop_table("loose_minifig")
