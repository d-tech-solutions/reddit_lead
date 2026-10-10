"""add match feed index

Revision ID: e5b2d84a9c17
Revises: d4a9c2e71f38
Create Date: 2026-07-31

The feed reads "this user's watchers, confirmed only, newest first". The three indexes already on
`matches` are single-column and none of them serves that: `ix_matches_watcher_id` finds the rows
but leaves an ORDER BY sort, and `ix_matches_llm_verified` is barely selective on a boolean.

Partial on `llm_verified IS TRUE` because rejected and unverified candidates are the bulk of this
table — the matcher writes a row for every candidate the vector gate produces, and only a minority
ever get confirmed. Keeping them out of the index keeps it small and lets Postgres skip the
recheck.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e5b2d84a9c17'
down_revision: Union[str, None] = 'd4a9c2e71f38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Column order matters: watcher_id first so the index can be probed per watcher, then the
    # feed's exact sort key. `id` is in there because timestamps are not unique — the matcher
    # writes several rows in one transaction — and the cursor pages on the pair.
    op.create_index(
        'ix_matches_feed',
        'matches',
        ['watcher_id', sa.text('created_at DESC'), sa.text('id DESC')],
        unique=False,
        postgresql_where=sa.text('llm_verified IS TRUE'),
    )
    # The unread badge, counted on every page load: same partial predicate, narrowed further.
    op.create_index(
        'ix_matches_unread',
        'matches',
        ['watcher_id'],
        unique=False,
        postgresql_where=sa.text('llm_verified IS TRUE AND read_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('ix_matches_unread', table_name='matches')
    op.drop_index('ix_matches_feed', table_name='matches')
