"""add users table and watchers.user_id

Revision ID: d4a9c2e71f38
Revises: c3f8a1b56e42
Create Date: 2026-07-30 00:00:00.000000

Note: `watchers.user_id` is NOT NULL, and watchers predating this migration have no owner to
assign. There is no correct value to invent for them, so the upgrade deletes them (and their
`matches` rows, via the existing cascade). At the time this was written that meant one seeded
development watcher. Re-create watchers through POST /api/v1/watchers.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4a9c2e71f38'
down_revision: Union[str, None] = 'c3f8a1b56e42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('clerk_user_id', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=True),
        sa.Column('plan', sa.String(length=20), nullable=False, server_default='free'),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_users_clerk_user_id'), 'users', ['clerk_user_id'], unique=True
    )
    op.create_index(op.f('ix_users_plan'), 'users', ['plan'], unique=False)

    # Ownerless watchers cannot satisfy the NOT NULL below. `matches` rows referencing them go too,
    # via matches_watcher_id_fkey ON DELETE CASCADE.
    op.execute('DELETE FROM watchers')

    op.add_column('watchers', sa.Column('user_id', sa.UUID(), nullable=False))
    op.create_foreign_key(
        'watchers_user_id_fkey', 'watchers', 'users', ['user_id'], ['id'], ondelete='CASCADE'
    )
    op.create_index(op.f('ix_watchers_user_id'), 'watchers', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_watchers_user_id'), table_name='watchers')
    op.drop_constraint('watchers_user_id_fkey', 'watchers', type_='foreignkey')
    op.drop_column('watchers', 'user_id')
    op.drop_index(op.f('ix_users_plan'), table_name='users')
    op.drop_index(op.f('ix_users_clerk_user_id'), table_name='users')
    op.drop_table('users')
