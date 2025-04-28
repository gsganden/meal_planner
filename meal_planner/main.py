import html
import json
import logging
import os
import re
import sqlite3
import uuid
from pathlib import Path
from typing import TypeVar

import apsw
import fasthtml.common as fh
import html2text
import httpx
import instructor
import monsterui.all as mu
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from starlette.datastructures import FormData
from starlette.requests import Request

from meal_planner.api.recipes import api_router, initialize_db
from meal_planner.models import Recipe

MODEL_NAME = "gemini-2.0-flash"
ACTIVE_RECIPE_EXTRACTION_PROMPT_FILE = (
    "20250428_165655__include_quantities_units_dont_mention_html.txt"
)

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompt_templates"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


openai_client = AsyncOpenAI(
    api_key=os.environ["GOOGLE_API_KEY"],
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

aclient = instructor.from_openai(openai_client)


app = fh.FastHTMLWithLiveReload(hdrs=(mu.Theme.blue.headers()))
rt = app.route


app.mount("/api/v1", api_router)


def create_html_cleaner() -> html2text.HTML2Text:
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.body_width = 0
    return h


HTML_CLEANER = create_html_cleaner()


@rt("/")
def get():
    return with_layout(mu.Titled("Meal Planner"))


def sidebar():
    nav = mu.NavContainer(
        fh.Li(
            fh.A(
                mu.DivFullySpaced("Meal Planner"),
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

    hamburger_button = fh.Div(
        mu.Button(
            mu.UkIcon("menu"),
            data_uk_toggle="target: #mobile-sidebar",
            cls="p-2",
        ),
        cls="md:hidden flex justify-end p-2",
    )

    mobile_sidebar_container = fh.Div(
        sidebar(),
        id="mobile-sidebar",
        hidden=True,
    )

    return (
        fh.Title("Meal Planner"),
        indicator_style,
        hamburger_button,
        mobile_sidebar_container,
        fh.Div(cls="flex flex-col md:flex-row w-full")(
            fh.Div(sidebar(), cls="hidden md:block w-1/5 max-w-52"),
            fh.Div(content, cls="md:w-4/5 w-full p-4", id="content"),
        ),
    )


@rt("/recipes/extract")
def get():
    url_input_group = fh.Div(
        mu.Input(
            id="recipe_url",
            name="recipe_url",
            type="url",
            placeholder="Enter recipe URL (optional)",
        ),
        mu.Button(
            "Fetch Text from URL",
            hx_post="/recipes/fetch-text",
            hx_target="#recipe_text",
            hx_swap="outerHTML",
            hx_include="[name='recipe_url']",
            hx_indicator="#fetch-indicator",
            margin="ml-2",
        ),
        mu.Loading(id="fetch-indicator", cls="htmx-indicator ml-2"),
        cls="flex items-center mb-4 mt-4",
    )

    text_area = mu.TextArea(
        id="recipe_text",
        name="recipe_text",
        placeholder="Paste recipe text here, or fetch from URL above.",
        rows=15,
        label="Recipe Text (Editable)",
    )

    extract_button_group = fh.Div(
        mu.Button(
            "Extract Recipe",
            hx_post="/recipes/extract/run",
            hx_target="#recipe-results",
            hx_swap="innerHTML",
            hx_include="#recipe_text",
            hx_indicator="#extract-indicator",
        ),
        mu.Loading(id="extract-indicator", cls="htmx-indicator ml-2"),
        cls="mt-4",
    )

    form = mu.Form(
        url_input_group,
        text_area,
        extract_button_group,
        id="recipe-input-form",
    )

    disclaimer = fh.P(
        "Recipe extraction uses AI and may not be perfectly accurate. Always "
        "double-check the results.",
        cls="text-sm text-gray-500 mt-4",
    )
    results_div = fh.Div(id="recipe-results")

    return with_layout(
        mu.Titled(
            "Extract Recipe",
            fh.Div(form, disclaimer, results_div),
            id="content",
        )
    )


async def fetch_page_text(recipe_url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
        "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=15.0, headers=headers
    ) as client:
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


async def fetch_and_clean_text_from_url(recipe_url: str) -> str:
    """Fetches and cleans text content from a URL."""
    logger.info("Fetching text from: %s", recipe_url)
    try:
        raw_text = await fetch_page_text(recipe_url)
        logger.info("Successfully fetched text from: %s", recipe_url)
    except httpx.RequestError as e:
        logger.error(
            "HTTP Request Error fetching page text from %s: %s",
            recipe_url,
            e,
            exc_info=True,
        )
        raise
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP Status Error fetching page text from %s: %s",
            recipe_url,
            e,
            exc_info=True,
        )
        raise
    except Exception as e:
        logger.error(
            "Error fetching page text from %s: %s", recipe_url, e, exc_info=True
        )
        raise RuntimeError(f"Failed to fetch or process URL: {recipe_url}") from e

    page_text = HTML_CLEANER.handle(raw_text)
    logger.info("Cleaned HTML text from: %s", recipe_url)
    return page_text


async def extract_recipe_from_text(page_text: str) -> Recipe:
    """Extracts and post-processes a recipe from text."""
    try:
        logging.info("Calling model %s for provided text", MODEL_NAME)
        extracted_recipe: Recipe = await call_llm(
            prompt=(
                PROMPT_DIR / "recipe_extraction" / ACTIVE_RECIPE_EXTRACTION_PROMPT_FILE
            )
            .read_text()
            .format(page_text=page_text),
            response_model=Recipe,
        )
        logging.info("Call to model %s successful for text", MODEL_NAME)
    except Exception as e:
        logger.error(
            "Error calling model %s for text: %s", MODEL_NAME, e, exc_info=True
        )
        raise
    processed_recipe = postprocess_recipe(extracted_recipe)
    return processed_recipe


async def extract_recipe_from_url(recipe_url: str) -> Recipe:
    """Fetches text from a URL and extracts a recipe from it."""
    return await extract_recipe_from_text(
        await fetch_and_clean_text_from_url(recipe_url)
    )


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
    return (
        _remove_leading_step_numbers(html.unescape(instruction))
        .replace(" ,", ",")
        .replace(" ;", ";")
        .strip()
    )


def _remove_leading_step_numbers(instruction: str) -> str:
    """Removes leading step numbers like "Step 1", "Step 1:", "1.", "1 " """
    return re.sub(
        r"^\s*(?:Step\s*\d+|\d+)\s*[:.]?\s*", "", instruction, flags=re.IGNORECASE
    ).strip()


def _close_parenthesis(text: str) -> str:
    """Appends a closing parenthesis if an opening one exists without a closing one."""
    if "(" in text and ")" not in text:
        return text + ")"
    return text


RECIPE_NAMESPACE_UUID = uuid.UUID("a5c1f7d3-0e9c-4b8e-8b7e-7d3f2c8e0b3d")


def _generate_recipe_id(name: str) -> str:
    stripped_name = name.strip()
    if not stripped_name:
        raise ValueError(
            "Recipe name cannot be empty or only whitespace for ID generation"
        )

    # Generate UUIDv5 based on the namespace and the stripped recipe name
    return str(uuid.uuid5(RECIPE_NAMESPACE_UUID, stripped_name))


@rt("/recipes/fetch-text")
async def post_fetch_text(recipe_url: str | None = None):
    if not recipe_url:
        logger.error("Fetch text called without URL.")
        return fh.Div("Please provide a Recipe URL to fetch.", cls="text-red-500 mb-4")

    try:
        logger.info("Fetching and cleaning text from URL: %s", recipe_url)
        cleaned_text = await fetch_and_clean_text_from_url(recipe_url)
        logger.info("Successfully processed URL for text: %s", recipe_url)
    except httpx.RequestError as e:
        logger.error(
            "HTTP Request Error fetching text from %s: %s",
            recipe_url,
            e,
            exc_info=False,
        )
        return fh.Div(
            f"Error fetching URL: {e}. Check URL/connection.",
            cls="text-red-500 mb-4",
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP Status Error fetching text from %s: %s", recipe_url, e, exc_info=False
        )
        return fh.Div(
            f"HTTP Error {e.response.status_code} fetching URL.",
            cls="text-red-500 mb-4",
        )
    except RuntimeError as e:
        logger.error(
            "Runtime error fetching text from %s: %s", recipe_url, e, exc_info=True
        )
        return fh.Div(f"Failed to process URL: {e}", cls="text-red-500 mb-4")
    except Exception as e:
        logger.error(
            "Unexpected error fetching text from %s: %s", recipe_url, e, exc_info=True
        )
        return fh.Div("Unexpected error fetching text.", cls="text-red-500 mb-4")

    return mu.TextArea(
        cleaned_text,
        id="recipe_text",
        name="recipe_text",
        rows=15,
        label="Recipe Text (Fetched or Manual)",
        placeholder="Paste recipe text here, or fetch from URL above.",
    )


@rt("/recipes/extract/run")
async def post(recipe_url: str | None = None, recipe_text: str | None = None):
    if not recipe_text:
        logging.error("Recipe extraction called without text.")
        return fh.Div("No text content provided for extraction.")

    try:
        log_source = "provided text"
        logger.info("Calling extraction logic for source: %s", log_source)
        processed_recipe = await extract_recipe_from_text(recipe_text)
        logger.info("Extraction successful for source: %s", log_source)
    except Exception as e:
        log_source = "provided text"
        logger.error(
            "Error during recipe extraction from %s: %s",
            log_source,
            e,
            exc_info=True,
        )
        return fh.Div(
            "Recipe extraction failed. An unexpected error occurred during processing."
        )

    hidden_fields = (
        fh.Input(type="hidden", name="name", value=processed_recipe.name),
        *(
            fh.Input(type="hidden", name="ingredients", value=ing)
            for ing in processed_recipe.ingredients
        ),
        *(
            fh.Input(type="hidden", name="instructions", value=inst)
            for inst in processed_recipe.instructions
        ),
    )

    save_button_container = fh.Div(
        mu.Button(
            "Save Recipe",
            hx_post="/recipes/save",
            hx_include="closest form",
            hx_target="#save-button-container",
            hx_swap="outerHTML",
        ),
        id="save-button-container",
        cls="mt-4",
    )

    return mu.Form(
        mu.TextArea(
            processed_recipe.markdown,
            label="Extracted Recipe",
            id="recipe_text_display",
            name="recipe_text_display",
            rows=25,
            disabled=True,
        ),
        hidden_fields,
        save_button_container,
        id="recipe-display-form",
    )


@rt("/recipes/save")
async def post_save_recipe(request: Request):
    table = initialize_db()
    form_data: FormData = await request.form()
    name = form_data.get("name")
    ingredients = form_data.getlist("ingredients")
    instructions = form_data.getlist("instructions")

    if not name:
        return fh.Span("Error: Recipe name is required.", cls="text-red-500")
    if not ingredients or not instructions:
        return fh.Span(
            "Error: Missing recipe ingredients or instructions.", cls="text-red-500"
        )

    try:
        new_id = _generate_recipe_id(name)
    except ValueError as e:
        logger.error("Error generating recipe ID for save: %s", e, exc_info=False)
        return fh.Span(f"Error: {e}", cls="text-red-500")

    db_data = {
        "id": new_id,
        "name": name,
        "ingredients": json.dumps(ingredients),
        "instructions": json.dumps(instructions),
    }

    try:
        table.insert(db_data)
        logger.info("Saved recipe via UI: %s, Name: %s", new_id, name)
    except apsw.ConstraintError as e:
        if "UNIQUE constraint failed: recipes.id" in str(e):
            logger.warning(
                "Attempted to save duplicate recipe name via UI: %s (ID: %s)",
                name,
                new_id,
            )
            return fh.Span(
                "Error: A recipe with this name already exists.", cls="text-red-500"
            )
        else:
            logger.error(
                "Database constraint error saving recipe via UI: %s", e, exc_info=True
            )
            return fh.Span(
                "Error saving recipe due to data conflict.", cls="text-red-500"
            )
    except Exception as e:
        logger.error("Database error saving recipe via UI: %s", e, exc_info=True)
        return fh.Span("Error saving recipe to database.", cls="text-red-500")

    return fh.Span("Recipe Saved Successfully!", cls="text-green-500")
