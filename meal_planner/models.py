from typing import Annotated, Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel

RecipeIngredients = Annotated[
    list[str],
    Field(description="List of ingredients", min_length=1),
]
RecipeInstructions = Annotated[
    list[str],
    Field(description="List of instructions", min_length=1),
]
RecipeName = Annotated[str, Field(description="The name of the recipe", min_length=1)]


# Model for creating a recipe - ensures validation via Annotated types
class RecipeCreate(SQLModel):  # Or BaseModel if it doesn't need to be a table model
    name: RecipeName
    ingredients: RecipeIngredients
    instructions: RecipeInstructions


class RecipeBase(SQLModel):
    name: RecipeName
    ingredients: list[str] = Field(sa_column=Column(JSON))
    instructions: list[str] = Field(sa_column=Column(JSON))

    @property
    def markdown(self) -> str:
        ingredients_md = "\n".join([f"- {i}" for i in self.ingredients])
        instructions_md = "\n".join([f"- {i}" for i in self.instructions])
        return (
            f"# {self.name}\n\n"
            f"## Ingredients\n{ingredients_md}\n\n"
            f"## Instructions\n{instructions_md}\n"
        )


class Recipe(RecipeBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
