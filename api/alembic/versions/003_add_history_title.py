"""Add title column to research_history

Revision ID: 003
Revises: 002
Create Date: 2026-03-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "research_history",
        sa.Column("title", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("research_history", "title")
