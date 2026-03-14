"""Initial schema — all 6 tables

Revision ID: 001
Revises: None
Create Date: 2026-03-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- topics ---
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(50), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )

    # --- channels ---
    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "topic_id",
            sa.Integer(),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("url", sa.String(255), nullable=False),
        sa.Column(
            "last_fetched", sa.DateTime(timezone=True), nullable=True
        ),
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
    )
    op.create_index(
        "uq_channel_topic_url", "channels", ["topic_id", "url"], unique=True
    )

    # --- strategies ---
    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "source_channel_id",
            sa.Integer(),
            sa.ForeignKey("channels.id"),
            nullable=True,
        ),
        sa.Column("source_videos", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column(
            "parameters", postgresql.JSONB(), server_default="[]", nullable=True
        ),
        sa.Column(
            "entry_rules", postgresql.JSONB(), server_default="[]", nullable=True
        ),
        sa.Column(
            "exit_rules", postgresql.JSONB(), server_default="[]", nullable=True
        ),
        sa.Column(
            "risk_management",
            postgresql.JSONB(),
            server_default="[]",
            nullable=True,
        ),
        sa.Column(
            "notes", postgresql.JSONB(), server_default="[]", nullable=True
        ),
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
    )
    op.create_index(
        "idx_strategies_fts",
        "strategies",
        [sa.text("to_tsvector('english', name || ' ' || COALESCE(description, ''))")],
        postgresql_using="gin",
    )

    # --- drafts ---
    op.create_table(
        "drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("strat_code", sa.Integer(), unique=True, nullable=False),
        sa.Column("strat_name", sa.String(255), nullable=False),
        sa.Column(
            "strategy_id",
            sa.Integer(),
            sa.ForeignKey("strategies.id"),
            nullable=True,
        ),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("todo_count", sa.Integer(), default=0),
        sa.Column(
            "todo_fields",
            postgresql.ARRAY(sa.Text()),
            server_default="{}",
            nullable=True,
        ),
        sa.Column("active", sa.Boolean(), default=False),
        sa.Column("tested", sa.Boolean(), default=False),
        sa.Column("prod", sa.Boolean(), default=False),
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
    )

    # --- research_history ---
    op.create_table(
        "research_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.String(20), nullable=False),
        sa.Column("url", sa.String(255), nullable=False),
        sa.Column(
            "channel_id",
            sa.Integer(),
            sa.ForeignKey("channels.id"),
            nullable=True,
        ),
        sa.Column(
            "topic_id",
            sa.Integer(),
            sa.ForeignKey("topics.id"),
            nullable=True,
        ),
        sa.Column(
            "researched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("strategies_found", sa.Integer(), default=0),
    )
    op.create_index(
        "uq_history_video_topic",
        "research_history",
        ["video_id", "topic_id"],
        unique=True,
    )

    # --- research_sessions ---
    op.create_table(
        "research_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(20), default="running"),
        sa.Column(
            "topic_id",
            sa.Integer(),
            sa.ForeignKey("topics.id"),
            nullable=True,
        ),
        sa.Column("step", sa.Integer(), default=0),
        sa.Column("step_name", sa.String(50), nullable=True),
        sa.Column("total_steps", sa.Integer(), default=6),
        sa.Column("channel", sa.String(100), nullable=True),
        sa.Column(
            "videos_processing",
            postgresql.ARRAY(sa.Text()),
            server_default="{}",
            nullable=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "completed_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("result_summary", postgresql.JSONB(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_research_sessions_active",
        "research_sessions",
        ["status"],
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_table("research_sessions")
    op.drop_table("research_history")
    op.drop_table("drafts")
    op.drop_table("strategies")
    op.drop_table("channels")
    op.drop_table("topics")
