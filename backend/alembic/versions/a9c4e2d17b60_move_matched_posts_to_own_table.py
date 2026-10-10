"""move matched posts to their own table

Revision ID: a9c4e2d17b60
Revises: 8a3d5e7f1b29
Create Date: 2026-10-10

`reddit_posts` becomes the matcher's work queue (a row exists only until the LLM has judged the
post) and confirmed posts move to a new `matched_posts` table. `matches` now holds confirmed rows
only and points at `matched_posts`; rejections are counted in `match_stats` and sampled into
`rejection_log`. `seen_posts` is the dedup memory that lets judged posts be deleted without being
re-ingested.

Also adds the supporting pieces: queue claim columns on `reddit_posts`, `users.last_active_at`
(for the 90-day inactivity retention), and a GIN index on `watchers.subreddits` so the
"watchers covering this subreddit" lookup is an index scan.

Destroys data: `reddit_posts`, `matches` and (through the FK) `notification_deliveries` are
truncated, because existing rows cannot be mapped onto the new shape. Fine in development; do not
run against a database whose matches matter.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a9c4e2d17b60'
down_revision: Union[str, None] = '8a3d5e7f1b29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('TRUNCATE TABLE reddit_posts, matches CASCADE')

    # --- New tables -------------------------------------------------------------------------
    op.create_table(
        'matched_posts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('reddit_post_id', sa.String(length=20), nullable=False),
        sa.Column('subreddit', sa.String(length=100), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('author', sa.String(length=100), nullable=True),
        sa.Column('permalink', sa.Text(), nullable=False),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column(
            'matched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_matched_posts_reddit_post_id'), 'matched_posts', ['reddit_post_id'], unique=True
    )
    op.create_index(
        'ix_matched_posts_feed',
        'matched_posts',
        [sa.text('fetched_at DESC'), sa.text('id DESC')],
    )
    op.create_index(
        'ix_matched_posts_subreddit_feed',
        'matched_posts',
        ['subreddit', sa.text('fetched_at DESC'), sa.text('id DESC')],
    )

    op.create_table(
        'seen_posts',
        sa.Column('reddit_post_id', sa.String(length=20), nullable=False),
        sa.Column(
            'seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.PrimaryKeyConstraint('reddit_post_id'),
    )
    op.create_index(op.f('ix_seen_posts_seen_at'), 'seen_posts', ['seen_at'])

    op.create_table(
        'match_stats',
        sa.Column('watcher_id', sa.UUID(), nullable=False),
        sa.Column('subreddit', sa.String(length=100), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('reviewed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('confirmed', sa.Integer(), server_default='0', nullable=False),
        sa.ForeignKeyConstraint(['watcher_id'], ['watchers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('watcher_id', 'subreddit', 'day'),
    )
    # Dashboard reads a window of days per watcher; the PK leads with watcher_id but the by-day
    # trend and cleanup scans filter on day alone.
    op.create_index('ix_match_stats_day', 'match_stats', ['day'])

    op.create_table(
        'rejection_log',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('watcher_id', sa.UUID(), nullable=False),
        sa.Column('subreddit', sa.String(length=100), nullable=False),
        sa.Column('reddit_post_id', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('permalink', sa.Text(), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('model', sa.String(length=50), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.ForeignKeyConstraint(['watcher_id'], ['watchers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_rejection_log_watcher_recent',
        'rejection_log',
        ['watcher_id', sa.text('created_at DESC')],
    )
    op.create_index(op.f('ix_rejection_log_created_at'), 'rejection_log', ['created_at'])

    # --- reddit_posts becomes the queue -----------------------------------------------------
    op.add_column(
        'reddit_posts', sa.Column('attempts', sa.Integer(), server_default='0', nullable=False)
    )
    op.add_column(
        'reddit_posts', sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index('ix_reddit_posts_queue', 'reddit_posts', ['fetched_at', 'locked_until'])

    # --- matches: confirmed rows only, pointing at matched_posts ----------------------------
    op.drop_index('ix_matches_feed', table_name='matches')
    op.drop_index('ix_matches_unread', table_name='matches')
    op.drop_index('ix_matches_pending_notification', table_name='matches')
    op.drop_index('ix_matches_pending_verification', table_name='matches')
    op.drop_index(op.f('ix_matches_llm_verified'), table_name='matches')
    op.drop_index(op.f('ix_matches_reddit_post_id'), table_name='matches')
    op.drop_constraint('uq_matches_pair', 'matches', type_='unique')
    op.drop_column('matches', 'reddit_post_id')  # takes the foreign key with it
    op.drop_column('matches', 'llm_verified')
    op.drop_column('matches', 'verified_at')

    op.add_column('matches', sa.Column('matched_post_id', sa.UUID(), nullable=False))
    op.create_foreign_key(
        'matches_matched_post_id_fkey',
        'matches',
        'matched_posts',
        ['matched_post_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.create_unique_constraint('uq_matches_pair', 'matches', ['watcher_id', 'matched_post_id'])
    op.create_index(op.f('ix_matches_matched_post_id'), 'matches', ['matched_post_id'])
    op.create_index(
        'ix_matches_feed', 'matches', ['watcher_id', sa.text('created_at DESC'), sa.text('id DESC')]
    )
    op.create_index(
        'ix_matches_unread', 'matches', ['watcher_id'], postgresql_where=sa.text('read_at IS NULL')
    )
    op.create_index(
        'ix_matches_pending_notification',
        'matches',
        ['created_at'],
        postgresql_where=sa.text('notified_at IS NULL'),
    )

    # --- users + watchers -------------------------------------------------------------------
    op.add_column(
        'users',
        sa.Column(
            'last_active_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_index(op.f('ix_users_last_active_at'), 'users', ['last_active_at'])
    op.create_index(
        'ix_watchers_subreddits_gin', 'watchers', ['subreddits'], postgresql_using='gin'
    )

    # These tables churn constantly (insert + delete), so default autovacuum thresholds leave dead
    # rows around long enough to bloat them. Vacuum after ~1% of rows change instead of 20%.
    for table in ('reddit_posts', 'seen_posts', 'rejection_log'):
        op.execute(
            f'ALTER TABLE {table} SET (autovacuum_vacuum_scale_factor = 0.01, '
            'autovacuum_vacuum_threshold = 100)'
        )


def downgrade() -> None:
    op.execute('TRUNCATE TABLE reddit_posts, matches CASCADE')

    op.drop_index('ix_watchers_subreddits_gin', table_name='watchers')
    op.drop_index(op.f('ix_users_last_active_at'), table_name='users')
    op.drop_column('users', 'last_active_at')

    op.drop_index('ix_matches_pending_notification', table_name='matches')
    op.drop_index('ix_matches_unread', table_name='matches')
    op.drop_index('ix_matches_feed', table_name='matches')
    op.drop_index(op.f('ix_matches_matched_post_id'), table_name='matches')
    op.drop_constraint('uq_matches_pair', 'matches', type_='unique')
    op.drop_constraint('matches_matched_post_id_fkey', 'matches', type_='foreignkey')
    op.drop_column('matches', 'matched_post_id')

    op.add_column('matches', sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('matches', sa.Column('llm_verified', sa.Boolean(), nullable=True))
    op.add_column('matches', sa.Column('reddit_post_id', sa.UUID(), nullable=False))
    op.create_foreign_key(
        'matches_reddit_post_id_fkey',
        'matches',
        'reddit_posts',
        ['reddit_post_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.create_unique_constraint('uq_matches_pair', 'matches', ['watcher_id', 'reddit_post_id'])
    op.create_index(op.f('ix_matches_reddit_post_id'), 'matches', ['reddit_post_id'])
    op.create_index(op.f('ix_matches_llm_verified'), 'matches', ['llm_verified'])
    op.create_index(
        'ix_matches_pending_verification',
        'matches',
        ['created_at'],
        postgresql_where=sa.text('llm_verified IS NULL'),
    )
    op.create_index(
        'ix_matches_pending_notification',
        'matches',
        ['verified_at'],
        postgresql_where=sa.text('llm_verified IS TRUE AND notified_at IS NULL'),
    )
    op.create_index(
        'ix_matches_feed',
        'matches',
        ['watcher_id', sa.text('created_at DESC'), sa.text('id DESC')],
        postgresql_where=sa.text('llm_verified IS TRUE'),
    )
    op.create_index(
        'ix_matches_unread',
        'matches',
        ['watcher_id'],
        postgresql_where=sa.text('llm_verified IS TRUE AND read_at IS NULL'),
    )

    op.drop_index('ix_reddit_posts_queue', table_name='reddit_posts')
    op.drop_column('reddit_posts', 'locked_until')
    op.drop_column('reddit_posts', 'attempts')

    op.drop_index(op.f('ix_rejection_log_created_at'), table_name='rejection_log')
    op.drop_index('ix_rejection_log_watcher_recent', table_name='rejection_log')
    op.drop_table('rejection_log')
    op.drop_index('ix_match_stats_day', table_name='match_stats')
    op.drop_table('match_stats')
    op.drop_index(op.f('ix_seen_posts_seen_at'), table_name='seen_posts')
    op.drop_table('seen_posts')
    op.drop_index('ix_matched_posts_subreddit_feed', table_name='matched_posts')
    op.drop_index('ix_matched_posts_feed', table_name='matched_posts')
    op.drop_index(op.f('ix_matched_posts_reddit_post_id'), table_name='matched_posts')
    op.drop_table('matched_posts')
