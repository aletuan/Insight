"""add vietnamese columns

Revision ID: a1b2c3d4e5f6
Revises: d4aa19918480
Create Date: 2026-03-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd4aa19918480'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Vietnamese translation columns."""
    op.add_column('items', sa.Column('summary_vi', sa.Text(), nullable=True))
    op.add_column('items', sa.Column('tags_vi', postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column('clusters', sa.Column('label_vi', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove Vietnamese translation columns."""
    op.drop_column('clusters', 'label_vi')
    op.drop_column('items', 'tags_vi')
    op.drop_column('items', 'summary_vi')
