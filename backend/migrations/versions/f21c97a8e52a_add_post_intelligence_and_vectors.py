"""add post intelligence and vectors

Revision ID: f21c97a8e52a
Revises: 939ab3f2355c
Create Date: 2026-07-01 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'f21c97a8e52a'
down_revision: Union[str, Sequence[str], None] = '939ab3f2355c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create pgvector extension if it doesn't exist
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # 2. Create reddit_post_intelligence table
    op.create_table('reddit_post_intelligence',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('post_id', sa.Integer(), nullable=False),
        sa.Column('problem', sa.Text(), nullable=True),
        sa.Column('industry', sa.String(length=100), nullable=True),
        sa.Column('services_needed', sa.JSON(), nullable=True),
        sa.Column('buying_intent', sa.String(length=50), nullable=True),
        sa.Column('urgency', sa.String(length=50), nullable=True),
        sa.Column('estimated_budget', sa.String(length=100), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('embedding', Vector(dim=1536), nullable=True),
        sa.Column('analyzed_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['post_id'], ['reddit_posts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('post_id')
    )
    op.create_index(op.f('ix_reddit_post_intelligence_id'), 'reddit_post_intelligence', ['id'], unique=False)
    op.create_index(op.f('ix_reddit_post_intelligence_post_id'), 'reddit_post_intelligence', ['post_id'], unique=True)

    # 3. Add embedding to user_preferences
    op.add_column('user_preferences', sa.Column('embedding', Vector(dim=1536), nullable=True))


def downgrade() -> None:
    # 1. Drop embedding column from user_preferences
    op.drop_column('user_preferences', 'embedding')

    # 2. Drop reddit_post_intelligence table
    op.drop_index(op.f('ix_reddit_post_intelligence_post_id'), table_name='reddit_post_intelligence')
    op.drop_index(op.f('ix_reddit_post_intelligence_id'), table_name='reddit_post_intelligence')
    op.drop_table('reddit_post_intelligence')
