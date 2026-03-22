"""Add backtest_jobs and backtest_results tables

Revision ID: 007
Revises: 006
Create Date: 2026-03-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- backtest_jobs ---
    op.create_table(
        "backtest_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "draft_strat_code",
            sa.Integer(),
            sa.ForeignKey("drafts.strat_code"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("start_date", sa.String(10), nullable=False),
        sa.Column("end_date", sa.String(10), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_backtest_jobs_status",
        ),
        sa.CheckConstraint(
            "start_date < end_date",
            name="ck_backtest_jobs_dates",
        ),
    )

    # Composite index for worker polling (WHERE status='pending' ORDER BY created_at)
    op.create_index(
        "ix_backtest_jobs_status_created",
        "backtest_jobs",
        ["status", "created_at"],
    )

    # Index for listing backtests per draft
    op.create_index(
        "ix_backtest_jobs_draft_strat_code",
        "backtest_jobs",
        ["draft_strat_code"],
    )

    # --- backtest_results ---
    op.create_table(
        "backtest_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("backtest_jobs.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column(
            "trades",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    # Drop results first to respect FK dependency (REQ-DM-15)
    op.drop_table("backtest_results")
    op.drop_table("backtest_jobs")
