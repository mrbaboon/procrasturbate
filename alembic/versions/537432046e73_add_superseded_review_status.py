"""add_superseded_review_status

Revision ID: 537432046e73
Revises: 1ecea3dd7b08
Create Date: 2025-12-14 01:12:30.495181

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '537432046e73'
down_revision: Union[str, None] = '1ecea3dd7b08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'superseded' value to reviewstatus enum
    op.execute("ALTER TYPE reviewstatus ADD VALUE IF NOT EXISTS 'superseded'")


def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values directly.
    # The enum value will remain but won't be used.
    pass
