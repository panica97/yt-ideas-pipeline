"""add data_from and data_to columns to instruments

Revision ID: 013
Revises: 012
Create Date: 2026-03-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instruments",
        sa.Column("data_from", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instruments",
        sa.Column("data_to", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("instruments", "data_to")
    op.drop_column("instruments", "data_from")
