"""add mode and debug columns to backtest_jobs

Revision ID: 011
Revises: 010
Create Date: 2026-03-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "backtest_jobs",
        sa.Column("mode", sa.String(20), server_default="simple", nullable=False),
    )
    op.add_column(
        "backtest_jobs",
        sa.Column("debug", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("backtest_jobs", "debug")
    op.drop_column("backtest_jobs", "mode")
