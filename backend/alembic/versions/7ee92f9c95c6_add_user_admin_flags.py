"""add user admin flags

Revision ID: 7ee92f9c95c6
Revises: 5184adb4da2a
Create Date: 2026-09-26 14:38:57.991654

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ee92f9c95c6'
down_revision: Union[str, None] = '5184adb4da2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Autogenerate also proposed dropping four `matches` partial indexes (ix_matches_feed,
# ix_matches_pending_notification, ix_matches_pending_verification, ix_matches_unread) — a false
# positive from how it diffs `postgresql_where` expressions, unrelated to this change. Left out on
# purpose; dropping them for real would break the match feed's query plan.


def upgrade() -> None:
    # `server_default` backfills the two existing rows in this table (there's no user-facing
    # feature yet, but the migration still needs to run against whatever's already there) —
    # `False`/`True` match the ORM-side defaults in `app.models.user.User`.
    op.add_column(
        'users',
        sa.Column('is_superadmin', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true())
    )


def downgrade() -> None:
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'is_superadmin')
