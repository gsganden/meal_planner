"""Pydantic and SQLModel data models for the Meal Planner application.

This module defines the core data models used throughout the application,
including both database models (SQLModel) and API request/response models.
"""

from datetime import datetime
from typing import Annotated, Optional

from pydantic import model_validator
from sqlalchemy import Column, func
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


class MakesRangeValidationError(ValueError):
    """Raised when makes_max is less than makes_min."""

    pass


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
        makes_min: Optional minimum quantity that the recipe makes (positive integer).
        makes_max: Optional maximum quantity that the recipe makes (positive integer).
        makes_unit: Optional unit for quantity (e.g., "servings", "cookies", "pieces").
    """

    name: RecipeName
    ingredients: RecipeIngredients
    instructions: RecipeInstructions
    makes_min: Optional[int] = Field(
        default=None, description="Minimum quantity that the recipe makes", ge=1
    )
    makes_max: Optional[int] = Field(
        default=None, description="Maximum quantity that the recipe makes", ge=1
    )
    makes_unit: Optional[str] = Field(
        default=None,
        description="Unit for the quantity (e.g., servings, cookies, pieces)",
    )

    @model_validator(mode="after")
    def validate_makes_range(self):
        """Validate that makes_max is not less than makes_min."""
        if (
            self.makes_max is not None
            and self.makes_min is not None
            and self.makes_max < self.makes_min
        ):
            raise MakesRangeValidationError(
                f"Maximum quantity ({self.makes_max}) cannot be less than minimum "
                f"quantity ({self.makes_min})"
            )
        return self

    @property
    def markdown(self) -> str:
        """Generate a markdown-formatted representation of the recipe.

        Creates a structured markdown document with the recipe name as a
        header, followed by makes info (if available), ingredients and
        instructions in bulleted lists. This format is used for display
        and for LLM prompts.

        Returns:
            A markdown string with H1 title, makes info, H2 sections for
            ingredients and instructions, each item as a bullet point.
        """
        makes_md = ""
        if self.makes_min is not None or self.makes_max is not None:
            unit = self.makes_unit or "servings"
            if self.makes_min == self.makes_max:
                makes_md = f"**Makes:** {self.makes_min} {unit}\n\n"
            elif self.makes_min is not None and self.makes_max is not None:
                makes_md = f"**Makes:** {self.makes_min}-{self.makes_max} {unit}\n\n"
            elif self.makes_min is not None:
                makes_md = f"**Makes:** {self.makes_min}+ {unit}\n\n"
            elif self.makes_max is not None:
                makes_md = f"**Makes:** up to {self.makes_max} {unit}\n\n"

        ingredients_md = "\n".join([f"- {i}" for i in self.ingredients])
        instructions_md = "\n".join([f"- {i}" for i in self.instructions])
        return (
            f"# {self.name}\n\n"
            f"{makes_md}"
            f"## Ingredients\n{ingredients_md}\n\n"
            f"## Instructions\n{instructions_md}\n"
        )


class Recipe(RecipeBase, table=True):
    """Database model for storing recipes with persistence.

    Extends RecipeBase to add database-specific fields and configuration.
    This model is used by SQLModel/SQLAlchemy for database operations.

    Attributes:
        id: Primary key, auto-generated on insert.
        name: Inherited from RecipeBase.
        ingredients: Inherited from RecipeBase, stored as JSON.
        instructions: Inherited from RecipeBase, stored as JSON.
        makes_min: Inherited from RecipeBase, optional minimum quantity.
        makes_max: Inherited from RecipeBase, optional maximum quantity.
        makes_unit: Inherited from RecipeBase, optional unit for quantity.
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
