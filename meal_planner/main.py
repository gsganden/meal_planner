import difflib
import html
import json
import logging
import os
import re
from pathlib import Path
from typing import TypeVar

import fasthtml.common as fh
import html2text
import httpx
import instructor
import monsterui.all as mu
from fastapi import FastAPI
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError
from starlette.datastructures import FormData
from starlette.requests import Request
from starlette.responses import Response, HTMLResponse
from starlette.staticfiles import StaticFiles

from meal_planner.api.recipes import api_router, recipes_table
from meal_planner.models import Recipe

MODEL_NAME = "gemini-2.0-flash"
ACTIVE_RECIPE_EXTRACTION_PROMPT_FILE = "20250428_205830__include_parens.txt"

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompt_templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

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

api_app = FastAPI()
api_app.include_router(api_router)

app.mount("/api", api_app)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
                        "Create",
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
        fh.Script(src="/static/main.js"),
    )


@rt("/recipes/extract")
def get():
    url_input_component = fh.Div(
        fh.Div(
            mu.Input(
                id="recipe_url",
                name="recipe_url",
                type="url",
                placeholder="https://example.com/recipe",
                cls="flex-grow mr-2 bg-white",
            ),
            fh.Div(
                mu.Button(
                    "Fetch Text from URL",
                    hx_post="/recipes/fetch-text",
                    hx_target="#recipe_text_container",
                    hx_swap="outerHTML",
                    hx_include="[name='recipe_url']",
                    hx_indicator="#fetch-indicator",
                    cls="bg-blue-500 hover:bg-blue-600 text-white",
                ),
                mu.Loading(id="fetch-indicator", cls="htmx-indicator ml-2"),
                cls="flex items-center",
            ),
            cls="flex items-end",
        ),
        cls="mb-4",
    )

    text_area_container = fh.Div(
        mu.TextArea(
            id="recipe_text",
            name="recipe_text",
            placeholder="Paste full recipe text here, or fetch from URL above.",
            rows=15,
            cls="mb-4 bg-white",
        ),
        id="recipe_text_container",
    )

    extract_button_group = fh.Div(
        mu.Button(
            "Extract Recipe",
            hx_post="/recipes/extract/run",
            hx_target="#recipe-results",
            hx_swap="innerHTML",
            hx_include="#recipe_text_container",
            hx_indicator="#extract-indicator",
            cls="bg-blue-500 hover:bg-blue-600 text-white",
        ),
        mu.Loading(id="extract-indicator", cls="htmx-indicator ml-2"),
        cls="mt-4",
    )

    disclaimer = fh.P(
        "Recipe extraction uses AI and may not be perfectly accurate. Always "
        "double-check the results.",
        cls="text-xs text-gray-500 mt-1",
    )

    results_div = fh.Div(id="recipe-results")

    input_section = fh.Div(
        fh.H2("Extract Recipe", cls="text-3xl mb-4"),
        fh.H3("URL", cls="text-xl mb-2"),
        url_input_component,
        fh.H3("Text", cls="text-xl mb-2 mt-4"),
        text_area_container,
        extract_button_group,
        disclaimer,
        results_div,
        cls="space-y-4 mb-6 p-4 border rounded bg-gray-50 mt-6",
    )

    edit_form_target_div = fh.Div(id="edit-form-target")

    return with_layout(
        mu.Titled(
            "Create Recipe",
            fh.Div(input_section, edit_form_target_div),
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
    logger.info("Extraction successful for source: %s", "provided text")
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
            _postprocess_ingredient(i) for i in recipe.ingredients if i.strip()
        ]
    if recipe.instructions:
        recipe.instructions = [
            _postprocess_instruction(i) for i in recipe.instructions if i.strip()
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


CSS_ERROR_CLASS = "text-red-500 mb-4"


def generate_diff_html(before_text: str, after_text: str) -> tuple[str, str]:
    """Generates two HTML strings showing a diff between before and after text."""
    before_lines = before_text.splitlines()
    after_lines = after_text.splitlines()
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines)
    before_html = []
    after_html = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in before_lines[i1:i2]:
                escaped_line = html.escape(line)
                before_html.append(escaped_line)
                after_html.append(escaped_line)
        elif tag == "replace":
            for line in before_lines[i1:i2]:
                before_html.append(f"<del>{html.escape(line)}</del>")
            for line in after_lines[j1:j2]:
                after_html.append(f"<ins>{html.escape(line)}</ins>")
        elif tag == "delete":
            for line in before_lines[i1:i2]:
                before_html.append(f"<del>{html.escape(line)}</del>")
        elif tag == "insert":
            for line in after_lines[j1:j2]:
                after_html.append(f"<ins>{html.escape(line)}</ins>")

    return "\n".join(before_html), "\n".join(after_html)


def _parse_recipe_form_data(form_data: FormData, prefix: str = "") -> dict:
    """Parses recipe form data into a dictionary, handling optional prefix."""
    name_value = form_data.get(f"{prefix}name")
    name = name_value if isinstance(name_value, str) else ""

    ingredients_values = form_data.getlist(f"{prefix}ingredients")
    ingredients = [
        ing for ing in ingredients_values if isinstance(ing, str) and ing.strip()
    ]

    instructions_values = form_data.getlist(f"{prefix}instructions")
    instructions = [
        inst for inst in instructions_values if isinstance(inst, str) and inst.strip()
    ]

    return {
        "name": name,
        "ingredients": ingredients,
        "instructions": instructions,
    }


def _build_diff_content(original_recipe: Recipe, current_markdown: str):
    """Builds the inner content for the diff view container."""
    before_html, after_html = generate_diff_html(
        original_recipe.markdown, current_markdown
    )
    pre_style = "white-space: pre-wrap; overflow-wrap: break-word;"

    before_area = fh.Div(
        fh.Strong("Original Recipe (Reference)"),
        fh.Pre(
            fh.Html(fh.NotStr(before_html)),
            cls="border p-2 rounded bg-gray-100 mt-1 overflow-auto text-xs",
            id="diff-before-pre",
            style=pre_style,
        ),
        cls="w-1/2",
    )
    after_area = fh.Div(
        fh.Strong("Current Edited Recipe"),
        fh.Pre(
            fh.Html(fh.NotStr(after_html)),
            cls="border p-2 rounded bg-gray-100 mt-1 overflow-auto text-xs",
            id="diff-after-pre",
            style=pre_style,
        ),
        cls="w-1/2",
    )
    return fh.Div(
        before_area, after_area, cls="flex space-x-4 mt-4", id="diff-content-wrapper"
    )


def _build_edit_review_form(
    current_recipe: Recipe,
    original_recipe: Recipe | None = None,
    modification_prompt_value: str | None = None,
    error_message_content=None,
):
    """Builds the structured, editable recipe form with live diff."""
    if original_recipe is None:
        original_recipe = current_recipe

    controls_section = _build_modification_controls(
        modification_prompt_value, error_message_content
    )
    original_hidden_fields = _build_original_hidden_fields(original_recipe)
    editable_section = _build_editable_section(current_recipe)
    review_section = _build_review_section(original_recipe, current_recipe)
    save_button_container = _build_save_button()

    combined_edit_section = fh.Div(
        fh.H2("Edit Recipe", cls="text-3xl mb-4"),
        controls_section,
        editable_section,
    )

    diff_style = fh.Style("""
        ins { background-color: #e6ffe6; text-decoration: none; }
        del { background-color: #ffe6e6; text-decoration: none; }
    """)

    return fh.Div(
        mu.Form(
            combined_edit_section,
            review_section,
            save_button_container,
            *original_hidden_fields,
            id="edit-review-form",
        ),
        diff_style,
    )


def _build_modification_controls(
    modification_prompt_value: str | None, error_message_content
):
    """Builds the 'Modify with AI' control section."""
    modification_input = mu.Input(
        id="modification_prompt",
        name="modification_prompt",
        placeholder="e.g., Make it vegan, double the servings",
        label="Modify Recipe Request (Optional)",
        value=modification_prompt_value or "",
        cls="mb-2 bg-white",
    )
    modify_button_container = fh.Div(
        mu.Button(
            "Modify Recipe",
            hx_post="/recipes/modify",
            hx_target="#edit-review-form",
            hx_swap="outerHTML",
            hx_include="closest form",
            hx_indicator="#modify-indicator",
            cls="bg-blue-500 hover:bg-blue-600 text-white",
        ),
        mu.Loading(id="modify-indicator", cls="htmx-indicator ml-2"),
        cls="mb-4",
    )
    edit_disclaimer = fh.P(
        "AI recipe modification is experimental. Review changes carefully.",
        cls="text-xs text-gray-500 mt-1 mb-4",
    )
    return fh.Div(
        fh.H3("Modify with AI", cls="text-xl mb-2"),
        modification_input,
        modify_button_container,
        edit_disclaimer,
        error_message_content or "",
        cls="mb-6",
    )


def _build_original_hidden_fields(original_recipe: Recipe):
    """Builds the hidden input fields for the original recipe data."""
    return (
        fh.Input(type="hidden", name="original_name", value=original_recipe.name),
        *(
            fh.Input(type="hidden", name="original_ingredients", value=ing)
            for ing in original_recipe.ingredients
        ),
        *(
            fh.Input(type="hidden", name="original_instructions", value=inst)
            for inst in original_recipe.instructions
        ),
    )


def _build_editable_section(current_recipe: Recipe):
    """Builds the 'Edit Manually' section with inputs for name, ingredients, and instructions."""
    name_input = _build_name_input(current_recipe.name)
    ingredients_section = _build_ingredients_section(current_recipe.ingredients)
    instructions_section = _build_instructions_section(current_recipe.instructions)

    return fh.Div(
        fh.H3("Edit Manually", cls="text-xl mb-4"),
        name_input,
        ingredients_section,
        instructions_section,
    )


def _build_name_input(name_value: str):
    """Builds the input field for the recipe name."""
    return mu.Input(
        id="name",
        name="name",
        label="Recipe Name",
        value=name_value,
        cls="mb-4 bg-white",
        hx_post="/recipes/ui/update-diff",
        hx_target="#diff-content-wrapper",
        hx_swap="innerHTML",
        hx_trigger="change, keyup changed delay:500ms",
        hx_include="closest form",
    )


def _build_ingredients_section(ingredients: list[str]):
    """Builds the ingredients list section with inputs and add/remove buttons."""
    ingredient_inputs = fh.Div(
        *(_build_ingredient_input(i, ing) for i, ing in enumerate(ingredients)),
        id="ingredients-list",
        cls="mb-4",
    )
    add_ingredient_button = mu.Button(
        mu.UkIcon("plus-circle"),
        hx_post="/recipes/ui/add-ingredient",
        hx_target="#ingredients-list",
        hx_swap="beforeend",
        cls="mb-4 text-green-500 hover:text-green-600 uk-border-circle p-1 flex items-center justify-center",
    )
    return fh.Div(
        fh.H3("Ingredients", cls="text-xl mb-2"),
        ingredient_inputs,
        add_ingredient_button,
    )


def _build_ingredient_input(index: int, value: str):
    """Builds a single ingredient input row."""
    return fh.Div(
        mu.Input(
            name="ingredients",
            value=value,
            placeholder="Ingredient",
            cls="flex-grow mr-2 bg-white",
            hx_post="/recipes/ui/update-diff",
            hx_target="#diff-content-wrapper",
            hx_swap="innerHTML",
            hx_trigger="change, keyup changed delay:500ms",
            hx_include="closest form",
        ),
        mu.Button(
            mu.UkIcon("minus-circle"),
            cls="ml-2 text-red-500 hover:text-red-600 uk-border-circle p-1 flex items-center justify-center delete-item-button",
            type="button",
        ),
        cls="flex items-center mb-2",
        id=f"ingredient-{index}",
    )


def _build_instructions_section(instructions: list[str]):
    """Builds the instructions list section with textareas and add/remove buttons."""
    instruction_items = [
        _build_instruction_input(i, inst) for i, inst in enumerate(instructions)
    ]
    instruction_inputs = fh.Div(
        *instruction_items,
        id="instructions-list",
        cls="mb-4",
    )
    add_instruction_button = mu.Button(
        mu.UkIcon("plus-circle"),
        hx_post="/recipes/ui/add-instruction",
        hx_target="#instructions-list",
        hx_swap="beforeend",
        cls="mb-4 text-green-500 hover:text-green-600 uk-border-circle p-1 flex items-center justify-center",
    )
    return fh.Div(
        fh.H3("Instructions", cls="text-xl mb-2"),
        instruction_inputs,
        add_instruction_button,
    )


def _build_instruction_input(index: int, value: str):
    """Builds a single instruction textarea row."""
    return fh.Div(
        mu.TextArea(
            value,  # Use the value directly
            name="instructions",
            placeholder="Instruction Step",
            rows=2,
            cls="flex-grow mr-2 bg-white",
            hx_post="/recipes/ui/update-diff",
            hx_target="#diff-content-wrapper",
            hx_swap="innerHTML",
            hx_trigger="change, keyup changed delay:500ms",
            hx_include="closest form",
        ),
        mu.Button(
            mu.UkIcon("minus-circle"),
            cls="ml-2 text-red-500 hover:text-red-600 uk-border-circle p-1 flex items-center justify-center delete-item-button",
            type="button",
        ),
        cls="flex items-start mb-2",
        id=f"instruction-{index}",
    )


def _build_review_section(original_recipe: Recipe, current_recipe: Recipe):
    """Builds the 'Review Changes' section with the diff view."""
    diff_content_wrapper = _build_diff_content(original_recipe, current_recipe.markdown)
    return fh.Div(
        fh.H2("Review Changes", cls="text-2xl mb-4"),
        diff_content_wrapper,
        cls="p-4 border rounded bg-gray-50 mt-6",
    )


def _build_save_button():
    """Builds the save button container."""
    return fh.Div(
        mu.Button(
            "Save Recipe",
            hx_post="/recipes/save",
            hx_target="#recipe-results",
            hx_swap="innerHTML",
            hx_include="closest form",
            hx_indicator="#save-indicator",
            cls="bg-blue-500 hover:bg-blue-600 text-white",
        ),
        mu.Loading(id="save-indicator", cls="htmx-indicator ml-2"),
        id="save-button-container",
        cls="mt-6",
    )


@rt("/recipes/fetch-text")
async def post_fetch_text(recipe_url: str | None = None):
    if not recipe_url:
        logger.error("Fetch text called without URL.")
        return fh.Div("Please provide a Recipe URL to fetch.", cls=CSS_ERROR_CLASS)

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
            "Error fetching URL. Please check the URL and your connection.",
            cls=CSS_ERROR_CLASS,
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP Status Error fetching text from %s: %s", recipe_url, e, exc_info=False
        )
        return fh.Div(
            "Error fetching URL: The server returned an error.",
            cls=CSS_ERROR_CLASS,
        )
    except RuntimeError as e:
        logger.error(
            "Runtime error fetching text from %s: %s", recipe_url, e, exc_info=True
        )
        return fh.Div(
            "Failed to process the content from the URL.", cls=CSS_ERROR_CLASS
        )
    except Exception as e:
        logger.error(
            "Unexpected error fetching text from %s: %s", recipe_url, e, exc_info=True
        )
        return fh.Div("Unexpected error fetching text.", cls=CSS_ERROR_CLASS)

    # Return the TextArea wrapped in the container div, with styling
    return fh.Div(
        mu.TextArea(
            cleaned_text,
            id="recipe_text",
            name="recipe_text",
            rows=15,
            placeholder="Paste recipe text here, or fetch from URL above.",
            cls="mb-4 bg-white",
        ),
        id="recipe_text_container",  # Match the original container ID
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
        logger.info(
            f"Instructions before building form: {processed_recipe.instructions}"
        )
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

    # Build the rendered text view
    reference_heading = fh.H2("Extracted Recipe (Reference)", cls="text-2xl mb-2 mt-6")
    rendered_content_div = fh.Div(
        fh.H3(processed_recipe.name, cls="text-xl font-bold mb-3"),
        fh.H4("Ingredients", cls="text-lg font-semibold mb-1"),
        fh.Ul(
            *[fh.Li(ing) for ing in processed_recipe.ingredients],
            cls="list-disc list-inside mb-3",
        ),
        fh.H4("Instructions", cls="text-lg font-semibold mb-1"),
        fh.Ul(
            *[fh.Li(inst) for inst in processed_recipe.instructions],
            cls="list-disc list-inside",
        ),
        cls="p-4 border rounded bg-gray-50 text-sm max-w-none",
    )
    rendered_recipe_html = fh.Div(
        reference_heading,
        rendered_content_div,
        cls="mb-6",
    )

    edit_form_html = _build_edit_review_form(processed_recipe, processed_recipe)

    oob_wrapper_div = fh.Div(
        edit_form_html,
        hx_swap_oob="innerHTML:#edit-form-target",
    )

    return rendered_recipe_html, oob_wrapper_div


@rt("/recipes/save")
async def post_save_recipe(request: Request):
    form_data: FormData = await request.form()
    try:
        parsed_data = _parse_recipe_form_data(form_data)
        recipe_obj = Recipe(**parsed_data)
    except ValidationError as e:
        logger.warning("Validation error saving recipe: %s", e, exc_info=False)
        # Generic message, details logged
        return fh.Span(
            "Invalid recipe data. Please check the fields.", cls=CSS_ERROR_CLASS
        )
    except Exception as e:
        logger.error("Error parsing form data during save: %s", e, exc_info=True)
        return fh.Span("Error processing form data.", cls=CSS_ERROR_CLASS)

    # Now that validation passed, we can proceed
    db_data = {
        "name": recipe_obj.name,
        "ingredients": json.dumps(recipe_obj.ingredients),
        "instructions": json.dumps(recipe_obj.instructions),
    }

    try:
        inserted_record = recipes_table.insert(db_data)
        logger.info(
            "Saved recipe via UI: %s, Name: %s",
            inserted_record["id"],
            recipe_obj.name,  # Log parsed name
        )
    except Exception as e:
        logger.error("Database error saving recipe via UI: %s", e, exc_info=True)
        return fh.Span(
            "Error saving recipe.",
            cls=CSS_ERROR_CLASS,
            id="save-modified-button-container",
        )

    return fh.Span(
        "Current Recipe Saved!",
        cls="text-green-500",  # Let's make save confirmation green again
        id="save-modified-button-container",
    )


@rt("/recipes/modify")
async def post_modify_recipe(request: Request):
    form_data: FormData = await request.form()
    (
        current_recipe,
        original_recipe,
        modification_prompt,
        error_response,
    ) = _parse_and_validate_modify_form(form_data)

    if error_response:
        return error_response

    # Handle empty prompt case
    if not modification_prompt:
        logger.info("Modification requested with empty prompt. Returning form.")
        error_message = fh.Div(
            "Please enter modification instructions.", cls=f"{CSS_ERROR_CLASS} mt-2"
        )
        form_content = _build_edit_review_form(
            current_recipe,
            original_recipe,
            "",
            error_message,
        )
        return form_content.children[0]

    # Request modification from LLM
    logger.info("Modifying recipe with prompt: %s", modification_prompt)
    modified_recipe, llm_error_message = await _request_recipe_modification(
        current_recipe, modification_prompt
    )

    # Handle LLM failure by re-rendering form with an error
    if llm_error_message:
        error_message = fh.Div(
            llm_error_message,
            cls=f"{CSS_ERROR_CLASS} mt-2",
        )
        form_content = _build_edit_review_form(
            current_recipe, original_recipe, modification_prompt, error_message
        )
        return form_content.children[0]

    # Pass validated original and LLM-processed recipe to build form
    form_content = _build_edit_review_form(modified_recipe, original_recipe)
    return form_content.children[0]


def _parse_and_validate_modify_form(
    form_data: FormData,
) -> tuple[Recipe | None, Recipe | None, str | None, HTMLResponse | None]:
    """Parses and validates form data for the modify recipe request."""
    try:
        current_data = _parse_recipe_form_data(form_data)
        original_data = _parse_recipe_form_data(form_data, prefix="original_")
        modification_prompt = form_data.get("modification_prompt", "")

        # Validate recipes
        original_recipe = Recipe(**original_data)
        current_recipe = Recipe(**current_data)

        return current_recipe, original_recipe, modification_prompt, None

    except ValidationError as e:
        logger.warning("Validation error on modify form submit: %s", e, exc_info=False)
        error_div = fh.Div(
            "Invalid recipe data. Please check the fields.", cls=CSS_ERROR_CLASS
        )
        # Wrap error div in HTMLResponse for direct return
        return None, None, None, HTMLResponse(content=str(error_div))
    except Exception as e:
        logger.error("Error parsing modify form data: %s", e, exc_info=True)
        error_div = fh.Div(
            "Error processing modification request form.", cls=CSS_ERROR_CLASS
        )
        # Wrap error div in HTMLResponse for direct return
        return None, None, None, HTMLResponse(content=str(error_div))


async def _request_recipe_modification(
    current_recipe: Recipe, modification_prompt: str
) -> tuple[Recipe | None, str | None]:
    """Requests recipe modification from LLM and handles errors."""
    try:
        modification_template = (
            PROMPT_DIR / "recipe_modification" / "20250429_183353__initial.txt"
        ).read_text()
        modification_full_prompt = modification_template.format(
            current_recipe_markdown=current_recipe.markdown,
            modification_prompt=modification_prompt,
        )
        modified_recipe: Recipe = await call_llm(
            prompt=modification_full_prompt,
            response_model=Recipe,
        )
        logger.info("LLM modification successful for prompt: %s", modification_prompt)
        processed_recipe = postprocess_recipe(modified_recipe)
        return processed_recipe, None  # Return recipe, no error message

    except Exception as e:
        logger.error(
            "Error during recipe modification for prompt '%s': %s",
            modification_prompt,
            e,
            exc_info=True,
        )
        # Return None for recipe, and the error message
        return None, "Recipe modification failed. An unexpected error occurred."


# --- HTMX UI Fragment Endpoints ---


@rt("/recipes/ui/add-ingredient", methods=["POST"])
def post_add_ingredient_row():
    return fh.Div(
        mu.Input(
            name="ingredients",
            value="",
            placeholder="New Ingredient",
            cls="flex-grow mr-2 bg-white",
            hx_post="/recipes/ui/update-diff",
            hx_target="#diff-content-wrapper",
            hx_swap="innerHTML",
            hx_trigger="change, keyup changed delay:500ms",
            hx_include="closest form",
        ),
        mu.Button(
            mu.UkIcon("minus-circle"),
            cls="ml-2 text-red-500 hover:text-red-600 uk-border-circle p-1 flex items-center justify-center delete-item-button",
            type="button",
        ),
        cls="flex items-center mb-2",
    )


@rt("/recipes/ui/add-instruction", methods=["POST"])
def post_add_instruction_row():
    return fh.Div(
        mu.TextArea(
            "",
            name="instructions",
            placeholder="New Instruction Step",
            rows=2,
            cls="flex-grow mr-2 bg-white",
            hx_post="/recipes/ui/update-diff",
            hx_target="#diff-content-wrapper",
            hx_swap="innerHTML",
            hx_trigger="change, keyup changed delay:500ms",
            hx_include="closest form",
        ),
        mu.Button(
            mu.UkIcon("minus-circle"),
            cls="ml-2 text-red-500 hover:text-red-600 uk-border-circle p-1 flex items-center justify-center delete-item-button",
            type="button",
        ),
        cls="flex items-start mb-2",
    )


@rt("/recipes/ui/remove-item", methods=["DELETE"])
def delete_remove_item():
    """Dummy endpoint for HTMX to target for removing elements.
    Returns 200 OK with no content, causing HTMX to remove the target.
    """
    return Response(status_code=200)


@rt("/recipes/ui/touch-name", methods=["POST"])
async def post_touch_name(request: Request):
    """Receives the name, returns the name input component.
    Used as a hack to trigger the name input's keyup/change handler,
    which in turn triggers the diff update after an item removal.
    """
    form_data = await request.form()
    name_value = form_data.get("name", "")
    # Return the exact same input component structure as in _build_edit_review_form
    return mu.Input(
        id="name",
        name="name",
        label="Recipe Name",
        value=name_value,
        cls="mb-4 bg-white",
        hx_post="/recipes/ui/update-diff",
        hx_target="#diff-content-wrapper",
        hx_swap="innerHTML",
        hx_trigger="change, keyup changed delay:500ms",
        hx_include="closest form",
    )


@rt("/recipes/ui/update-diff", methods=["POST"])
async def post_update_diff(request: Request):
    """Updates the diff view based on current form data."""
    form_data = await request.form()
    try:
        current_data = _parse_recipe_form_data(form_data)
        original_data = _parse_recipe_form_data(form_data, prefix="original_")

        # Validate both original and current data before generating diff
        original_recipe = Recipe(**original_data)
        current_recipe = Recipe(**current_data)

    except ValidationError as e:
        # Handle case where form data is temporarily invalid during editing
        logger.debug(
            "Validation error during diff update (expected during edit): %s", e
        )
        # Return the specific error state div
        return fh.Div(
            "Recipe state invalid for diff",
            id="diff-content-wrapper",
            cls="text-orange-500",
        )
    except Exception as e:
        # Catch other potential errors (e.g., form parsing)
        logger.error("Error preparing data for diff view: %s", e, exc_info=True)
        return fh.Div(
            "Error preparing data for diff",
            id="diff-content-wrapper",
            cls=CSS_ERROR_CLASS,
        )

    # If validation passes, generate the diff
    try:
        logger.debug("Updating diff: Original vs Current")
        diff_content_wrapper = _build_diff_content(
            original_recipe, current_recipe.markdown
        )
        return diff_content_wrapper
    except Exception as e:
        # Catch errors during diff generation itself
        logger.error("Error generating diff view: %s", e, exc_info=True)
        return fh.Div(
            "Error generating diff view",
            id="diff-content-wrapper",
            cls=CSS_ERROR_CLASS,
        )
