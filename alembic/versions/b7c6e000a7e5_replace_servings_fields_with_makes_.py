"""Replace servings fields with makes fields

Revision ID: b7c6e000a7e5
Revises: 47bdb0e75fe9
Create Date: 2025-06-19 12:55:44.918706

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b7c6e000a7e5"
down_revision: Union[str, None] = "47bdb0e75fe9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new makes fields
    op.add_column("recipes", sa.Column("makes_min", sa.Integer(), nullable=True))
    op.add_column("recipes", sa.Column("makes_max", sa.Integer(), nullable=True))
    op.add_column("recipes", sa.Column("makes_unit", sa.String(), nullable=True))

    # Drop old servings fields
    op.drop_column("recipes", "servings_min")
    op.drop_column("recipes", "servings_max")


def downgrade() -> None:
    """Downgrade schema."""
    # Add back servings fields
    op.add_column("recipes", sa.Column("servings_min", sa.Integer(), nullable=True))
    op.add_column("recipes", sa.Column("servings_max", sa.Integer(), nullable=True))

    # Drop makes fields
    op.drop_column("recipes", "makes_unit")
    op.drop_column("recipes", "makes_max")
    op.drop_column("recipes", "makes_min")
