"""add notification settings

Revision ID: 495ba81c6fcf
Revises: f6b1e4a92c73
Create Date: 2026-09-18 02:42:02.964245

Note: autogenerate also proposed dropping `matches`' four partial indexes
(`ix_matches_feed`, `ix_matches_unread`, `ix_matches_pending_verification`,
`ix_matches_pending_notification`) because their `postgresql_where` predicates aren't declared on
the `Match` model, only in the migrations that created them — a known autogenerate false positive,
not an intended change. Dropped from this revision.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '495ba81c6fcf'
down_revision: Union[str, None] = 'f6b1e4a92c73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notification_channels',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('channel_type', sa.String(length=20), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('verified', sa.Boolean(), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'channel_type', name='uq_notification_channels_user_type'),
    )
    op.create_index(
        op.f('ix_notification_channels_user_id'), 'notification_channels', ['user_id'], unique=False
    )
    op.add_column('users', sa.Column('notification_email', sa.String(length=320), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'notification_email')
    op.drop_index(op.f('ix_notification_channels_user_id'), table_name='notification_channels')
    op.drop_table('notification_channels')
