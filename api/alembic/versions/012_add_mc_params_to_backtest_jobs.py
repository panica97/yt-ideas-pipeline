"""add n_paths and fit_years columns to backtest_jobs

Revision ID: 012
Revises: 011
Create Date: 2026-03-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "backtest_jobs",
        sa.Column("n_paths", sa.Integer(), nullable=True),
    )
    op.add_column(
        "backtest_jobs",
        sa.Column("fit_years", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("backtest_jobs", "fit_years")
    op.drop_column("backtest_jobs", "n_paths")
