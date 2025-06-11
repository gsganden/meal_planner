"""convert_recipe_id_to_uuid

Revision ID: 3a4b5c6d7e8f
Revises: 2a3b4c5d6e7f
Create Date: 2025-06-10 12:00:00.000000

"""

from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "3a4b5c6d7e8f"
down_revision: Union[str, None] = "2a3b4c5d6e7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create new recipes table with UUID ID
    op.create_table(
        "recipes_new",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("ingredients", sa.JSON(), nullable=False),
        sa.Column("instructions", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # Copy data from old table to new table with UUID conversion
    connection = op.get_bind()

    # Get all existing recipes
    recipes = connection.execute(
        sa.text(
            "SELECT id, name, ingredients, instructions, "
            "created_at, updated_at FROM recipes"
        )
    ).fetchall()

    # Insert into new table with UUID IDs
    for recipe in recipes:
        new_uuid = str(uuid4())  # Standard UUID format with dashes
        connection.execute(
            sa.text("""
                INSERT INTO recipes_new (
                    id, name, ingredients, instructions, created_at, updated_at
                )
                VALUES (
                    :id, :name, :ingredients, :instructions, :created_at, :updated_at
                )
            """),
            {
                "id": new_uuid,
                "name": recipe.name,
                "ingredients": recipe.ingredients,
                "instructions": recipe.instructions,
                "created_at": recipe.created_at,
                "updated_at": recipe.updated_at,
            },
        )

    # Drop old table and rename new table
    op.drop_table("recipes")
    op.rename_table("recipes_new", "recipes")


def downgrade() -> None:
    """Downgrade schema."""
    # Create old recipes table with integer ID
    op.create_table(
        "recipes_old",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("ingredients", sa.JSON(), nullable=False),
        sa.Column("instructions", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # Copy data back with auto-generated integer IDs
    connection = op.get_bind()

    recipes = connection.execute(
        sa.text(
            "SELECT name, ingredients, instructions, "
            "created_at, updated_at FROM recipes"
        )
    ).fetchall()

    for recipe in recipes:
        connection.execute(
            sa.text("""
                INSERT INTO recipes_old (
                    name, ingredients, instructions, created_at, updated_at
                )
                VALUES (
                    :name, :ingredients, :instructions, :created_at, :updated_at
                )
            """),
            {
                "name": recipe.name,
                "ingredients": recipe.ingredients,
                "instructions": recipe.instructions,
                "created_at": recipe.created_at,
                "updated_at": recipe.updated_at,
            },
        )

    # Drop new table and rename old table
    op.drop_table("recipes")
    op.rename_table("recipes_old", "recipes")
