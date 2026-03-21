"""Add instruments table with seed data for common futures

Revision ID: 006
Revises: 005
Create Date: 2026-03-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- instruments ---
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(20), unique=True, nullable=False),
        sa.Column("sec_type", sa.String(10), nullable=False),
        sa.Column("exchange", sa.String(20), nullable=False),
        sa.Column("currency", sa.String(5), nullable=False, server_default="USD"),
        sa.Column("multiplier", sa.Float(), nullable=False),
        sa.Column("min_tick", sa.Float(), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
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

    # --- seed data: common futures ---
    op.execute(
        """
        INSERT INTO instruments (symbol, sec_type, exchange, currency, multiplier, min_tick) VALUES
            ('ES',  'FUT', 'CME',   'USD', 50,    0.25),
            ('NQ',  'FUT', 'CME',   'USD', 20,    0.25),
            ('MES', 'FUT', 'CME',   'USD', 5,     0.25),
            ('MNQ', 'FUT', 'CME',   'USD', 2,     0.25),
            ('CL',  'FUT', 'NYMEX', 'USD', 1000,  0.01),
            ('GC',  'FUT', 'COMEX', 'USD', 100,   0.10),
            ('MGC', 'FUT', 'COMEX', 'USD', 10,    0.10),
            ('GF',  'FUT', 'CME',   'USD', 500,   0.00025),
            ('OJ',  'FUT', 'ICE',   'USD', 15000, 0.05),
            ('RTY', 'FUT', 'CME',   'USD', 50,    0.10),
            ('YM',  'FUT', 'CBOT',  'USD', 5,     1.00),
            ('ZB',  'FUT', 'CBOT',  'USD', 1000,  0.03125),
            ('ZN',  'FUT', 'CBOT',  'USD', 1000,  0.015625),
            ('SI',  'FUT', 'COMEX', 'USD', 5000,  0.005),
            ('HG',  'FUT', 'COMEX', 'USD', 25000, 0.0005),
            ('NG',  'FUT', 'NYMEX', 'USD', 10000, 0.001)
        """
    )


def downgrade() -> None:
    op.drop_table("instruments")
