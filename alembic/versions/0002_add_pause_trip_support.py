"""Add pause_started_at and total_paused_seconds to monitoring_sessions.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-26 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'monitoring_sessions',
        sa.Column('pause_started_at', sa.DateTime(), nullable=True)
    )
    op.add_column(
        'monitoring_sessions',
        sa.Column('total_paused_seconds', sa.Float(), server_default='0.0', nullable=False)
    )


def downgrade() -> None:
    op.drop_column('monitoring_sessions', 'total_paused_seconds')
    op.drop_column('monitoring_sessions', 'pause_started_at')
