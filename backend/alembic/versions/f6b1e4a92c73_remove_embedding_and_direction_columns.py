"""remove embedding and direction columns

Revision ID: f6b1e4a92c73
Revises: e5b2d84a9c17
Create Date: 2026-08-18

The matcher no longer does vector retrieval — every active watcher subscribed to a post's
subreddit goes straight into a single batched LLM call per post (see docs/matcher/README.md).
That removes every column that only existed to support the vector gate: the pgvector columns on
`watchers` and `reddit_posts`, the HNSW index, and `watchers.direction` (the LLM now judges
direction fresh from `intent_text` and the post on every call, rather than from a stored label).
`matches.similarity`/`direction_score`/`adjusted_score` go too, since nothing computes them
anymore — `llm_verified`/`llm_reason`/`llm_model` and every partial index on `matches` are
untouched, including `ix_matches_pending_verification`, which the new single-stage design still
uses to find candidates awaiting a verdict.

Drops real data: any embedding computed so far, and every watcher's declared direction. Same
documented tradeoff as migration d4a9c2e71f38 — there is nothing to migrate the vectors *to*.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f6b1e4a92c73'
down_revision: Union[str, None] = 'e5b2d84a9c17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIMENSIONS = 1536


def upgrade() -> None:
    op.drop_index('ix_watchers_intent_embedding_hnsw', table_name='watchers')
    op.drop_index('ix_watchers_pending_embedding', table_name='watchers')
    op.drop_index('ix_reddit_posts_pending_embedding', table_name='reddit_posts')

    op.drop_column('watchers', 'intent_embedding')
    op.drop_column('watchers', 'embedded_at')
    op.drop_column('reddit_posts', 'embedding')
    op.drop_column('reddit_posts', 'embedded_at')
    op.drop_column('watchers', 'direction')

    op.drop_column('matches', 'similarity')
    op.drop_column('matches', 'direction_score')
    op.drop_column('matches', 'adjusted_score')


def downgrade() -> None:
    # Imported lazily, same reasoning as b7e1f3c9d024: alembic loads every migration file to build
    # the revision graph regardless of whether it runs, and `pgvector` isn't an installed
    # dependency now that nothing uses the vector columns it types.
    import pgvector.sqlalchemy

    # Nullable on the way back in: the dropped values cannot be reconstructed, so there is nothing
    # to backfill a NOT NULL default from.
    op.add_column('matches', sa.Column('adjusted_score', sa.Float(), nullable=True))
    op.add_column('matches', sa.Column('direction_score', sa.Float(), nullable=True))
    op.add_column('matches', sa.Column('similarity', sa.Float(), nullable=True))

    op.add_column(
        'watchers',
        sa.Column('direction', sa.String(length=20), nullable=False, server_default='requesting'),
    )
    op.add_column(
        'reddit_posts', sa.Column('embedded_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'reddit_posts',
        sa.Column('embedding', pgvector.sqlalchemy.Vector(EMBEDDING_DIMENSIONS), nullable=True),
    )
    op.add_column('watchers', sa.Column('embedded_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'watchers',
        sa.Column(
            'intent_embedding', pgvector.sqlalchemy.Vector(EMBEDDING_DIMENSIONS), nullable=True
        ),
    )

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
    op.create_index(
        'ix_watchers_intent_embedding_hnsw',
        'watchers',
        ['intent_embedding'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_with={'m': 16, 'ef_construction': 64},
        postgresql_ops={'intent_embedding': 'vector_cosine_ops'},
    )
