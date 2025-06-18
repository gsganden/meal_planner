"""Pydantic and SQLModel data models for the Meal Planner application.

This module defines the core data models used throughout the application,
including both database models (SQLModel) and API request/response models.
"""

from datetime import datetime
from typing import Annotated, Optional

from sqlalchemy import Column, func
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel

RecipeIngredients = Annotated[
    list[str],
    Field(description="List of ingredients", min_length=1, sa_column=Column(JSON)),
]
RecipeInstructions = Annotated[
    list[str],
    Field(
        ..., description="List of instructions", min_length=1, sa_column=Column(JSON)
    ),
]
RecipeName = Annotated[
    str, Field(..., description="The name of the recipe", min_length=1)
]


class RecipeBase(SQLModel):
    """Base recipe model with core fields shared across all recipe types.

    This model serves as the foundation for both database models and
    API request/response models. It includes validation for required
    fields and provides utility methods for recipe formatting.

    Attributes:
        name: The recipe name, must be non-empty.
        ingredients: List of ingredient strings, must contain at least one item.
        instructions: List of cooking instruction steps.
        source: Optional source URL or reference for the recipe.
    """

    name: RecipeName
    ingredients: RecipeIngredients
    instructions: RecipeInstructions
    source: Optional[str] = Field(
        default=None, description="Optional source URL or reference for the recipe"
    )

    @property
    def markdown(self) -> str:
        """Generate a markdown-formatted representation of the recipe.

        Creates a structured markdown document with the recipe name as a
        header, followed by source (if present), ingredients and instructions
        in bulleted lists. This format is used for display and for LLM prompts.

        Returns:
            A markdown string with H1 title, optional source, H2 sections for
            ingredients and instructions, each item as a bullet point.
        """
        ingredients_md = "\n".join([f"- {i}" for i in self.ingredients])
        instructions_md = "\n".join([f"- {i}" for i in self.instructions])

        result = f"# {self.name}\n\n"

        if self.source:
            result += f"**Source:** {self.source}\n\n"

        result += f"## Ingredients\n{ingredients_md}\n\n"
        result += f"## Instructions\n{instructions_md}\n"

        return result


class Recipe(RecipeBase, table=True):
    """Database model for storing recipes with persistence.

    Extends RecipeBase to add database-specific fields and configuration.
    This model is used by SQLModel/SQLAlchemy for database operations.

    Attributes:
        id: Primary key, auto-generated on insert.
        name: Inherited from RecipeBase.
        ingredients: Inherited from RecipeBase, stored as JSON.
        instructions: Inherited from RecipeBase, stored as JSON.
        created_at: Timestamp of when the recipe was created (UTC).
            This is a database-managed field. It will be `None` in Python
            before an object is persisted but will always be populated for
            records retrieved from the database.
        updated_at: Timestamp of when the recipe was last updated (UTC).
            This is a database-managed field. It will be `None` in Python
            before an object is persisted but will always be populated for
            records retrieved from the database.
    """

    __tablename__ = "recipes"  # type: ignore[assignment]
    id: Optional[int] = Field(default=None, primary_key=True)
    # SQLite limitations require manual timestamp management in application code.
    # These server defaults are kept for database portability and direct SQL operations.
    created_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs={"nullable": False, "server_default": func.now()},
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs={
            "nullable": False,
            "server_default": func.now(),
            "onupdate": func.now(),
        },
    )
