"""add stress test params to backtest jobs

Revision ID: 016
Revises: 015
Create Date: 2026-03-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "backtest_jobs",
        sa.Column("stress_test_name", sa.String(100), nullable=True),
    )
    op.add_column(
        "backtest_jobs",
        sa.Column("stress_param_overrides", JSONB, nullable=True),
    )
    op.add_column(
        "backtest_jobs",
        sa.Column("stress_single_overrides", JSONB, nullable=True),
    )
    op.add_column(
        "backtest_jobs",
        sa.Column("stress_max_parallel", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("backtest_jobs", "stress_max_parallel")
    op.drop_column("backtest_jobs", "stress_single_overrides")
    op.drop_column("backtest_jobs", "stress_param_overrides")
    op.drop_column("backtest_jobs", "stress_test_name")
