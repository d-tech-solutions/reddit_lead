"""add embedding columns to reddit_posts and watchers

Revision ID: b7e1f3c9d024
Revises: a2c4d2d568f4
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e1f3c9d024'
down_revision: Union[str, None] = 'a2c4d2d568f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIMENSIONS = 1536


def upgrade() -> None:
    # Imported lazily: alembic loads every migration file to build the revision graph, even when
    # not running this one, and `pgvector` is no longer an installed dependency now that the
    # embedding columns this migration adds have themselves been removed downstream (see
    # f6b1e4a92c73). A top-level import broke every alembic command on a fresh install.
    import pgvector.sqlalchemy

    op.add_column(
        'reddit_posts',
        sa.Column('embedding', pgvector.sqlalchemy.Vector(EMBEDDING_DIMENSIONS), nullable=True),
    )
    op.add_column(
        'reddit_posts',
        sa.Column('embedded_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'watchers',
        sa.Column(
            'intent_embedding', pgvector.sqlalchemy.Vector(EMBEDDING_DIMENSIONS), nullable=True
        ),
    )
    op.add_column(
        'watchers',
        sa.Column('embedded_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Partial indexes on the NULL rows: the backfill sweep's hot query is "find unembedded rows",
    # and these keep it cheap as the tables grow.
    op.create_index(
        'ix_reddit_posts_pending_embedding',
        'reddit_posts',
        ['fetched_at'],
        unique=False,
        postgresql_where=sa.text('embedding IS NULL'),
    )
    op.create_index(
        'ix_watchers_pending_embedding',
        'watchers',
        ['created_at'],
        unique=False,
        postgresql_where=sa.text('intent_embedding IS NULL'),
    )

    # HNSW index for cosine distance on the watcher side only. The matcher searches watchers for
    # each incoming post, so that is the read path worth indexing; reddit_posts takes constant
    # inserts and nothing queries it by vector yet, so indexing it would be write cost for no gain.
    op.create_index(
        'ix_watchers_intent_embedding_hnsw',
        'watchers',
        ['intent_embedding'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_with={'m': 16, 'ef_construction': 64},
        postgresql_ops={'intent_embedding': 'vector_cosine_ops'},
    )


def downgrade() -> None:
    op.drop_index('ix_watchers_intent_embedding_hnsw', table_name='watchers')
    op.drop_index('ix_watchers_pending_embedding', table_name='watchers')
    op.drop_index('ix_reddit_posts_pending_embedding', table_name='reddit_posts')
    op.drop_column('watchers', 'embedded_at')
    op.drop_column('watchers', 'intent_embedding')
    op.drop_column('reddit_posts', 'embedded_at')
    op.drop_column('reddit_posts', 'embedding')
