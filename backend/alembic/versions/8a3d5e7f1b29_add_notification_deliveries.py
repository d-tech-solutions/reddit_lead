"""add notification deliveries

Revision ID: 8a3d5e7f1b29
Revises: 7ee92f9c95c6
Create Date: 2026-10-06

One row per (match, channel) the notify worker has tried to deliver. See
app/models/notification_delivery.py.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = '8a3d5e7f1b29'
down_revision: Union[str, None] = '7ee92f9c95c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notification_deliveries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('match_id', sa.UUID(), nullable=False),
        sa.Column('channel_type', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('match_id', 'channel_type', name='uq_notification_deliveries_pair'),
    )
    op.create_index(
        op.f('ix_notification_deliveries_match_id'),
        'notification_deliveries',
        ['match_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_notification_deliveries_match_id'), table_name='notification_deliveries')
    op.drop_table('notification_deliveries')
