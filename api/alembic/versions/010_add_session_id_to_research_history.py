"""add session_id to research_history

Revision ID: 010
Revises: 009
Create Date: 2026-03-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "research_history",
        sa.Column("session_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_research_history_session_id",
        "research_history",
        "research_sessions",
        ["session_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_research_history_session_id",
        "research_history",
        type_="foreignkey",
    )
    op.drop_column("research_history", "session_id")
