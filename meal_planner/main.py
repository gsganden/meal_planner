import logging
import os
import textwrap
from pathlib import Path
from typing import TypeVar

import fasthtml.common as fh
import html2text
import httpx
import instructor
import monsterui.all as mu
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

MODEL_NAME = "gemini-2.0-flash"
ACTIVE_RECIPE_EXTRACTION_PROMPT_FILE = "20250426_212535__extract_instructions.txt"

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompt_templates"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def _check_api_key():
    if "GOOGLE_API_KEY" not in os.environ:
        logger.error("GOOGLE_API_KEY environment variable not set.")
        raise SystemExit("GOOGLE_API_KEY environment variable not set.")


_check_api_key()

openai_client = AsyncOpenAI(
    api_key=os.environ["GOOGLE_API_KEY"],
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

aclient = instructor.from_openai(openai_client)

app = fh.FastHTMLWithLiveReload(hdrs=(mu.Theme.blue.headers()))
rt = app.route


def create_html_cleaner() -> html2text.HTML2Text:
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.body_width = 0
    return h


HTML_CLEANER = create_html_cleaner()


@rt("/")
def get():
    return with_layout(mu.Titled("Home"))


def sidebar():
    nav = mu.NavContainer(
        fh.Li(
            fh.A(
                mu.DivFullySpaced("Home"),
                href="/",
                hx_target="#content",
                hx_push_url="true",
            )
        ),
        mu.NavParentLi(
            fh.A(mu.DivFullySpaced("Recipes")),
            mu.NavContainer(
                fh.Li(
                    fh.A(
                        "Extract",
                        href="/recipes/extract",
                        hx_target="#content",
                        hx_push_url="true",
                    )
                ),
                parent=False,
            ),
        ),
        uk_nav=True,
        cls=mu.NavT.primary,
    )
    return fh.Div(nav, cls="space-y-4 p-4 w-full md:w-full")


def with_layout(content):
    indicator_style = fh.Style("""
        .htmx-indicator { opacity: 0; transition: opacity 200ms ease-in; }
        .htmx-indicator.htmx-request { opacity: 1; }
    """)
    return (
        fh.Title("Meal Planner"),
        indicator_style,
        fh.Div(cls="flex flex-col md:flex-row w-full")(
            fh.Div(sidebar(), cls="hidden md:block w-1/5 max-w-52"),
            fh.Div(content, cls="md:w-4/5 w-full p-4", id="content"),
        ),
    )


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
    )
    instructions: list[str] = Field(
        description=(
            "List of instructions for the recipe, as Markdown-formatted strings."
        ),
    )


@rt("/recipes/extract")
def get():
    initial_form = mu.Form(
        mu.Input(
            id="recipe_url",
            name="recipe_url",
            type="url",
            placeholder="Enter Recipe URL",
        ),
        fh.Div(
            mu.Button("Extract Recipe"),
            mu.Loading(
                id="extract-indicator",
                cls="htmx-indicator ml-2",
            ),
        ),
        hx_post="/recipes/extract/run",
        hx_target="#recipe-results",
        hx_swap="innerHTML",
        hx_indicator="#extract-indicator",
        id="extract-form",
    )
    results_div = fh.Div(id="recipe-results")
    return with_layout(
        mu.Titled("Extract Recipe", fh.Div(initial_form, results_div), id="content")
    )


async def fetch_page_text(recipe_url: str):
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        response = await client.get(recipe_url)
    response.raise_for_status()
    return response.text


class ContainsRecipe(BaseModel):
    contains_recipe: bool = Field(
        ..., description="Whether the provided text contains a recipe (True or False)"
    )


T = TypeVar("T", bound=BaseModel)


async def call_llm(prompt: str, response_model: type[T]) -> T:
    response = await aclient.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "user", "content": prompt},
        ],
        response_model=response_model,
    )
    return response


async def extract_recipe_from_url(recipe_url: str) -> Recipe:
    """Fetches, cleans, extracts, and post-processes a recipe from a URL."""
    try:
        raw_text = await fetch_page_text(recipe_url)
        logger.info("Successfully fetched text from: %s", recipe_url)
    except Exception as e:
        logger.error(
            "Error fetching page text from %s: %s",
            recipe_url,
            e,
            exc_info=True,
        )
        raise
    page_text = HTML_CLEANER.handle(raw_text)

    try:
        logging.info(f"Calling model {MODEL_NAME} for URL: {recipe_url}")
        extracted_recipe: Recipe = await call_llm(
            prompt=(
                PROMPT_DIR / "recipe_extraction" / ACTIVE_RECIPE_EXTRACTION_PROMPT_FILE
            )
            .read_text()
            .format(page_text=page_text),
            response_model=Recipe,
        )
        logging.info(f"Call to model {MODEL_NAME} successful for URL: {recipe_url}")
    except Exception as e:
        logger.error(
            f"Error calling model {MODEL_NAME} for URL {recipe_url}: %s",
            e,
            exc_info=True,
        )
        raise
    processed_recipe = postprocess_recipe(extracted_recipe)
    return processed_recipe


def postprocess_recipe(recipe: Recipe) -> Recipe:
    """Post-processes the extracted recipe data."""
    if recipe.name:
        recipe.name = _postprocess_recipe_name(recipe.name)
    if recipe.ingredients:
        recipe.ingredients = [
            _postprocess_ingredient(i)
            for i in recipe.ingredients
            if i  # remove empty strings
        ]
    if recipe.instructions:
        recipe.instructions = [
            _postprocess_instruction(i)
            for i in recipe.instructions
            if i  # remove empty strings
        ]

    return recipe


def _postprocess_recipe_name(name: str) -> str:
    """Cleans and standardizes the recipe name."""
    return _close_parenthesis(
        name.strip().removesuffix("recipe").removesuffix("Recipe").title().strip()
    )


def _postprocess_ingredient(ingredient: str) -> str:
    """Cleans and standardizes a single ingredient string."""
    return _close_parenthesis(" ".join(ingredient.split()).strip().replace(" ,", ","))


def _postprocess_instruction(instruction: str) -> str:
    """Cleans and standardizes a single instruction string."""
    return instruction.replace(" ,", ",").replace(" ;", ";").strip()


def _close_parenthesis(text: str) -> str:
    """Appends a closing parenthesis if an opening one exists without a closing one."""
    if "(" in text and ")" not in text:
        return text + ")"
    return text


@rt("/recipes/extract/run")
async def post(recipe_url: str):
    try:
        processed_recipe = await extract_recipe_from_url(recipe_url)
        ingredients_md = "\n".join([f"- {i}" for i in processed_recipe.ingredients])
        instructions_md = "\n".join([f"- {i}" for i in processed_recipe.instructions])
        recipe_text = (
            f"# {processed_recipe.name}\n\n"
            f"## Ingredients\n{ingredients_md}\n\n"
            f"## Instructions\n{instructions_md}\n"
        )
        return mu.Form(
            mu.TextArea(
                recipe_text,
                label="Recipe",
                id="recipe_text",
                name="recipe_text",
                rows=25,
            ),
            id="recipe-edit-form",
        )
    except httpx.RequestError as e:
        logger.error(
            "HTTP Request Error extracting recipe from %s: %s",
            recipe_url,
            e,
            exc_info=True,
        )
        return fh.Div(f"Error fetching URL: {e}. Please check the URL and try again.")
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP Status Error extracting recipe from %s: %s",
            recipe_url,
            e,
            exc_info=True,
        )
        return fh.Div(
            f"Error fetching URL: Received status {e.response.status_code}. Please "
            "check the URL."
        )
    except Exception as e:
        logger.error(
            "Generic error processing recipe from %s: %s", recipe_url, e, exc_info=True
        )
        return fh.Div("Recipe extraction failed. An unexpected error occurred.")


fh.serve()
