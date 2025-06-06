"""add_timestamps_to_recipes_table

Revision ID: 1c66282b9e50
Revises: 1c2c47357c10
Create Date: 2025-06-05 16:02:23.986408

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "1c66282b9e50"
down_revision: Union[str, None] = "1c2c47357c10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite doesn't support adding columns with non-constant defaults
    # We need to add nullable columns first, then populate them, then make them non-null

    # Add created_at column as nullable first
    op.add_column(
        "recipes",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Add updated_at column as nullable first
    op.add_column(
        "recipes",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Populate timestamps for existing rows
    op.execute(
        "UPDATE recipes SET created_at = CURRENT_TIMESTAMP, "
        "updated_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
    )

    # For SQLite, we can't easily alter columns to be NOT NULL with defaults
    # The columns will remain nullable but our Python model handles this


def downgrade() -> None:
    """Downgrade schema."""
    # Remove the columns in reverse order
    op.drop_column("recipes", "updated_at")
    op.drop_column("recipes", "created_at")
