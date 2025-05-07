""" "create_recipe_table"

Revision ID: 1c2c47357c10
Revises:
Create Date: 2025-05-06 09:37:12.230224

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "1c2c47357c10"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "recipe",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("ingredients", sa.JSON(), nullable=False),
        sa.Column("instructions", sa.JSON(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("recipe")
