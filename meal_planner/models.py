from typing import Annotated

from pydantic import BaseModel, Field

RecipeId = Annotated[int, Field(..., description="Unique identifier for the recipe")]
RecipeIngredients = Annotated[
    list[str],
    Field(..., description="List of ingredients", min_length=1),
]
RecipeInstructions = Annotated[
    list[str],
    Field(..., description="List of instructions"),
]
RecipeName = Annotated[
    str, Field(..., description="The name of the recipe", min_length=1)
]


class RecipeData(BaseModel):
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


class Recipe(RecipeData):
    id: RecipeId
