from typing import Annotated, Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel

RecipeIngredients = Annotated[
    list[str],
    Field(description="List of ingredients", min_length=1, sa_column=Column(JSON)),
]
RecipeInstructions = Annotated[
    list[str],
    Field(..., description="List of instructions"),
]
RecipeName = Annotated[
    str, Field(..., description="The name of the recipe", min_length=1)
]


class RecipeBase(SQLModel):
    name: RecipeName
    ingredients: RecipeIngredients
    instructions: RecipeInstructions

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
