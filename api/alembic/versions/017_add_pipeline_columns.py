"""add pipeline columns to backtest jobs

Revision ID: 017
Revises: 016
Create Date: 2026-04-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "backtest_jobs",
        sa.Column("pipeline_group", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "backtest_jobs",
        sa.Column("pipeline_config", JSONB, nullable=True),
    )
    op.create_index(
        "idx_backtest_jobs_pipeline_group",
        "backtest_jobs",
        ["pipeline_group"],
        postgresql_where=sa.text("pipeline_group IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_backtest_jobs_pipeline_group", table_name="backtest_jobs")
    op.drop_column("backtest_jobs", "pipeline_config")
    op.drop_column("backtest_jobs", "pipeline_group")
