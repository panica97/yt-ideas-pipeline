"""add jobs table

Revision ID: 017
Revises: 016
Create Date: 2026-04-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(36), unique=True, nullable=False),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("draft_id", sa.String(255), nullable=False),
        sa.Column("config", JSONB, nullable=True),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("jobs")
