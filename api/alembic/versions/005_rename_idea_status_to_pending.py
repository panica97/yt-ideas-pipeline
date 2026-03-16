"""Rename default status from 'idea' to 'pending'

Revision ID: 005
Revises: 004
Create Date: 2026-03-16

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename existing 'idea' rows to 'pending'
    op.execute("UPDATE strategies SET status = 'pending' WHERE status = 'idea'")
    # Update server default
    op.alter_column(
        "strategies",
        "status",
        server_default="pending",
    )


def downgrade() -> None:
    op.execute("UPDATE strategies SET status = 'idea' WHERE status = 'pending'")
    op.alter_column(
        "strategies",
        "status",
        server_default="idea",
    )
