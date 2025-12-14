"""add model and prompts to reviews

Revision ID: 7922745ef546
Revises: 41dabc7f67fc
Create Date: 2025-12-14 01:57:01.086661

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7922745ef546'
down_revision: Union[str, None] = '41dabc7f67fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reviews', sa.Column('model', sa.String(length=100), nullable=True))
    op.add_column('reviews', sa.Column('system_prompt', sa.Text(), nullable=True))
    op.add_column('reviews', sa.Column('user_prompt', sa.Text(), nullable=True))
    # Index for filtering/searching by model
    op.create_index('ix_reviews_model', 'reviews', ['model'])


def downgrade() -> None:
    op.drop_index('ix_reviews_model', table_name='reviews')
    op.drop_column('reviews', 'user_prompt')
    op.drop_column('reviews', 'system_prompt')
    op.drop_column('reviews', 'model')
