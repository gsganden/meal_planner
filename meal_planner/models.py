import textwrap

from pydantic import BaseModel, Field
from markdown_it import MarkdownIt

md = MarkdownIt()


class Recipe(BaseModel):
    name: str = Field(
        ...,
        description=(
            textwrap.dedent(
                """\
                    The exact name of the dish as found in the text, including all
                    punctuation. Should NOT include the word "recipe".
                """
            )
        ),
    )
    ingredients: list[str] = Field(
        description="List of ingredients for the recipe, as raw strings.",
        min_length=1,
    )
    instructions: list[str] = Field(
        description=(
            "List of instructions for the recipe, as Markdown-formatted strings."
        ),
        min_length=1,
    )

    @property
    def markdown(self) -> str:
        ingredients_md = "\n".join([f"- {i}" for i in self.ingredients])
        instructions_md = "\n".join([f"- {i}" for i in self.instructions])
        return (
            f"# {self.name}\n\n"
            f"## Ingredients\n{ingredients_md}\n\n"
            f"## Instructions\n{instructions_md}\n"
        )


class RecipeRead(Recipe):
    id: int
