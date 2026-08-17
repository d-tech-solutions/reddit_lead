"""add matches table and watchers.direction

Revision ID: c3f8a1b56e42
Revises: b7e1f3c9d024
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3f8a1b56e42'
down_revision: Union[str, None] = 'b7e1f3c9d024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'watchers',
        sa.Column(
            'direction',
            sa.String(length=20),
            nullable=False,
            server_default='requesting',
        ),
    )

    op.create_table(
        'matches',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('watcher_id', sa.UUID(), nullable=False),
        sa.Column('reddit_post_id', sa.UUID(), nullable=False),
        sa.Column('similarity', sa.Float(), nullable=False),
        sa.Column('direction_score', sa.Float(), nullable=False),
        sa.Column('adjusted_score', sa.Float(), nullable=False),
        sa.Column('llm_verified', sa.Boolean(), nullable=True),
        sa.Column('llm_reason', sa.Text(), nullable=True),
        sa.Column('llm_model', sa.String(length=50), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['watcher_id'], ['watchers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reddit_post_id'], ['reddit_posts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        # One row per (watcher, post). Makes re-running the matcher over a post idempotent.
        sa.UniqueConstraint('watcher_id', 'reddit_post_id', name='uq_matches_pair'),
    )
    op.create_index(op.f('ix_matches_watcher_id'), 'matches', ['watcher_id'], unique=False)
    op.create_index(op.f('ix_matches_reddit_post_id'), 'matches', ['reddit_post_id'], unique=False)
    op.create_index(op.f('ix_matches_llm_verified'), 'matches', ['llm_verified'], unique=False)

    # The verifier's work queue: candidates written but not yet judged.
    op.create_index(
        'ix_matches_pending_verification',
        'matches',
        ['created_at'],
        unique=False,
        postgresql_where=sa.text('llm_verified IS NULL'),
    )
    # The notification worker's queue: confirmed matches nobody has been told about.
    op.create_index(
        'ix_matches_pending_notification',
        'matches',
        ['verified_at'],
        unique=False,
        postgresql_where=sa.text('llm_verified IS TRUE AND notified_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('ix_matches_pending_notification', table_name='matches')
    op.drop_index('ix_matches_pending_verification', table_name='matches')
    op.drop_index(op.f('ix_matches_llm_verified'), table_name='matches')
    op.drop_index(op.f('ix_matches_reddit_post_id'), table_name='matches')
    op.drop_index(op.f('ix_matches_watcher_id'), table_name='matches')
    op.drop_table('matches')
    op.drop_column('watchers', 'direction')
