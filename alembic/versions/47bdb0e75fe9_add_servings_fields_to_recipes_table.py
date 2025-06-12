"""add_servings_fields_to_recipes_table

Revision ID: 47bdb0e75fe9
Revises: 1c66282b9e50
Create Date: 2025-06-11 11:35:39.720238

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "47bdb0e75fe9"
down_revision: Union[str, None] = "1c66282b9e50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add servings_min column (nullable integer)
    op.add_column(
        "recipes",
        sa.Column(
            "servings_min",
            sa.Integer(),
            nullable=True,
        ),
    )

    # Add servings_max column (nullable integer)
    op.add_column(
        "recipes",
        sa.Column(
            "servings_max",
            sa.Integer(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Use batch operations for SQLite compatibility
    with op.batch_alter_table("recipes", schema=None) as batch_op:
        batch_op.drop_column("servings_max")
        batch_op.drop_column("servings_min")
