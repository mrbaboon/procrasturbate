"""add_check_run_id_to_reviews

Revision ID: 41dabc7f67fc
Revises: 537432046e73
Create Date: 2025-12-14 01:13:34.222529

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '41dabc7f67fc'
down_revision: Union[str, None] = '537432046e73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reviews', sa.Column('github_check_run_id', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('reviews', 'github_check_run_id')
