"""clean_up_integer_ids

Revision ID: 8dda03f6f2c2
Revises: 07760d4f0aad
Create Date: 2025-06-22 10:55:00.000000

"""

from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "8dda03f6f2c2"
down_revision: Union[str, None] = "07760d4f0aad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Clean up any remaining integer IDs by converting them to UUIDs."""
    connection = op.get_bind()

    # Check for integer-like IDs in recipes table and convert them
    recipes_with_int_ids = connection.execute(
        sa.text("SELECT id, name FROM recipes WHERE CAST(id AS INTEGER) = id")
    ).fetchall()

    for recipe in recipes_with_int_ids:
        old_id = recipe.id
        new_uuid = str(uuid4())

        # Update the recipe with a new UUID
        connection.execute(
            sa.text("UPDATE recipes SET id = :new_id WHERE id = :old_id"),
            {"new_id": new_uuid, "old_id": old_id},
        )
        print(f"Converted recipe ID {old_id} -> {new_uuid}")

    # Check for integer-like IDs in users table and convert them
    users_with_int_ids = connection.execute(
        sa.text("SELECT id, username FROM users WHERE CAST(id AS INTEGER) = id")
    ).fetchall()

    for user in users_with_int_ids:
        old_id = user.id
        new_uuid = str(uuid4())

        # Update the user with a new UUID
        connection.execute(
            sa.text("UPDATE users SET id = :new_id WHERE id = :old_id"),
            {"new_id": new_uuid, "old_id": old_id},
        )
        print(f"Converted user ID {old_id} -> {new_uuid}")

    print("Integer ID cleanup completed")


def downgrade() -> None:
    """Downgrade not supported - cannot convert UUIDs back to integers."""
    raise NotImplementedError(
        "Cannot downgrade UUID cleanup - would lose data integrity"
    )
