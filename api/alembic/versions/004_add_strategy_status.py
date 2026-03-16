"""Add status column to strategies

Revision ID: 004
Revises: 003
Create Date: 2026-03-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "strategies",
        sa.Column("status", sa.String(20), nullable=False, server_default="idea"),
    )
    op.create_index("idx_strategies_status", "strategies", ["status"])


def downgrade() -> None:
    op.drop_index("idx_strategies_status", table_name="strategies")
    op.drop_column("strategies", "status")
