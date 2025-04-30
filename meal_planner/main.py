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
from pydantic import BaseModel, Field
from starlette.datastructures import FormData
from starlette.requests import Request
from starlette.responses import Response

from meal_planner.api.recipes import api_router, recipes_table
from meal_planner.models import Recipe

MODEL_NAME = "gemini-2.0-flash"
ACTIVE_RECIPE_EXTRACTION_PROMPT_FILE = "20250428_205830__include_parens.txt"

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

api_app = FastAPI()
api_app.include_router(api_router)

app.mount("/api", api_app)


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
        fh.Script("""
            document.body.addEventListener('click', function(event) {
                // Use closest to handle clicks on the icon inside the button
                var deleteButton = event.target.closest('.delete-item-button');
                if (deleteButton) {
                    console.log('Delete button clicked:', deleteButton);
                    event.preventDefault(); // Stop default button action

                    var rowToRemove = deleteButton.closest('div');
                    var form = document.getElementById('edit-review-form');

                    if (!rowToRemove || !form) {
                        console.error('Could not find row to remove or the form.');
                        return;
                    }

                    console.log('Initiating DELETE request for row:', rowToRemove);
                    htmx.ajax('DELETE', '/recipes/ui/remove-item', {
                        target: rowToRemove,
                        swap: 'outerHTML'
                    }).then(function(response) {
                        // This runs after the DELETE request is successful AND the swap has started
                        // The DOM element might be gone, but the data should be reflected for the next request
                        console.log('DELETE request successful. Initiating POST for diff update...');
                        htmx.ajax('POST', '/recipes/ui/update-diff', {
                            source: form,
                            target: '#diff-content-wrapper',
                            swap: 'innerHTML'
                        });
                        console.log('Update diff POST request triggered.');
                    }).catch(function(error) {
                        console.error('Error during DELETE or subsequent POST:', error);
                    });
                }
            });
        """),
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

    # Add the empty div for the edit form target (outside input_section)
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


def _create_button_with_indicator(
    label: str,
    hx_post: str,
    hx_target: str,
    indicator_id: str,
    include_selector: str,
    container_id: str | None = None,
    extra_classes: str = "",
):
    """Helper function to create a Div containing a Button and Loading indicator."""
    button = mu.Button(
        label,
        hx_post=hx_post,
        hx_include=include_selector,
        hx_target=hx_target,
        hx_indicator=f"#{indicator_id}",
    )
    loader = mu.Loading(id=indicator_id, cls="htmx-indicator ml-2")
    return fh.Div(button, loader, id=container_id, cls=f"mt-2 {extra_classes}".strip())


def _parse_recipe_from_form(form_data: FormData, prefix: str = "") -> Recipe:
    """Parses recipe data from form fields with an optional prefix."""
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

    return Recipe(
        name=name,
        ingredients=ingredients,
        instructions=instructions,
    )


def _build_diff_content(original_recipe: Recipe, current_text: str):
    """Builds the inner content for the diff view container."""
    before_html, after_html = generate_diff_html(original_recipe.markdown, current_text)
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

    # Ensure we always have an 'original' recipe object, even if it's same as current
    if original_recipe is None:
        original_recipe = current_recipe

    # --- Modification Controls ---
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
    controls_section = fh.Div(
        fh.H3("Modify with AI", cls="text-xl mb-2"),
        modification_input,
        modify_button_container,
        edit_disclaimer,
        error_message_content or "",
        cls="mb-6",
    )

    # --- Original Recipe Hidden Fields (Always included now) ---
    original_hidden_fields = (
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

    # --- Editable Form Sections (Based on current_recipe) ---
    name_input = mu.Input(
        id="name",
        name="name",
        label="Recipe Name",
        value=current_recipe.name,
        cls="mb-4 bg-white",
        hx_post="/recipes/ui/update-diff",
        hx_target="#diff-content-wrapper",
        hx_swap="innerHTML",
        hx_trigger="change, keyup changed delay:500ms",
        hx_include="closest form",
    )

    ingredient_inputs = fh.Div(
        *(
            fh.Div(
                mu.Input(
                    name="ingredients",
                    value=ing,
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
                id=f"ingredient-{i}",
            )
            for i, ing in enumerate(current_recipe.ingredients)
        ),
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
    ingredients_section = fh.Div(
        fh.H3("Ingredients", cls="text-xl mb-2"),
        ingredient_inputs,
        add_ingredient_button,
    )

    instruction_items = [
        fh.Div(
            mu.TextArea(
                inst,
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
            id=f"instruction-{i}",
        )
        for i, inst in enumerate(current_recipe.instructions)
    ]
    if not instruction_items:
        instruction_items.append(
            fh.Div(
                mu.TextArea(
                    "",
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
                id="instruction-empty",
            )
        )
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
    instructions_section = fh.Div(
        fh.H3("Instructions", cls="text-xl mb-2"),
        instruction_inputs,
        add_instruction_button,
    )

    editable_section = fh.Div(
        fh.H3("Edit Manually", cls="text-xl mb-4"),
        name_input,
        ingredients_section,
        instructions_section,
    )

    # --- Review Section (Always rendered now) ---
    diff_content_wrapper = _build_diff_content(original_recipe, current_recipe.markdown)
    diff_style = fh.Style("""
        ins { background-color: #e6ffe6; text-decoration: none; }
        del { background-color: #ffe6e6; text-decoration: none; }
    """)

    review_section = fh.Div(
        fh.H2("Review Changes", cls="text-2xl mb-4"),
        diff_content_wrapper,
        cls="p-4 border rounded bg-gray-50 mt-6",
    )

    # --- Combined Edit Box ---
    combined_edit_section = fh.Div(
        fh.H2("Edit Recipe", cls="text-3xl mb-4"),
        controls_section,
        editable_section,
    )

    # --- Save Button ---
    save_button_container = fh.Div(
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
            f"Error fetching URL: {e}. Check URL/connection.",
            cls=CSS_ERROR_CLASS,
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP Status Error fetching text from %s: %s", recipe_url, e, exc_info=False
        )
        return fh.Div(
            f"HTTP Error {e.response.status_code} fetching URL.",
            cls=CSS_ERROR_CLASS,
        )
    except RuntimeError as e:
        logger.error(
            "Runtime error fetching text from %s: %s", recipe_url, e, exc_info=True
        )
        return fh.Div(f"Failed to process URL: {e}", cls=CSS_ERROR_CLASS)
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
            cls="mb-4 bg-white",  # Ensure white background
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
        # Build structure using fasthtml components
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
        # Removed fh.Html(), apply box styling, removed prose
        cls="p-4 border rounded bg-gray-50 text-sm max-w-none",
    )
    rendered_recipe_html = fh.Div(
        reference_heading,
        rendered_content_div,
        cls="mb-6",
    )

    # Build the editable form
    edit_form_html = _build_edit_review_form(processed_recipe, processed_recipe)

    # Create a new wrapper div for the OOB swap
    oob_wrapper_div = fh.Div(
        edit_form_html,  # Place the form inside the wrapper
        # Add the OOB attribute to the wrapper itself
        hx_swap_oob="innerHTML:#edit-form-target",
    )

    # Return the reference HTML normally, and the OOB wrapper div
    return rendered_recipe_html, oob_wrapper_div


@rt("/recipes/save")
async def post_save_recipe(request: Request):
    form_data: FormData = await request.form()

    # Use the parsing function to get cleaned data
    try:
        # Note: This assumes _parse_recipe_from_form handles potential errors
        # or returns a Recipe object even with missing fields for validation below.
        parsed_recipe = _parse_recipe_from_form(form_data)
    except Exception as e:
        # If parsing itself fails unexpectedly
        logger.error("Error parsing recipe from form during save: %s", e, exc_info=True)
        return fh.Span("Error processing form data.", cls=CSS_ERROR_CLASS)

    # Validate using the parsed Recipe object
    if not parsed_recipe.name:
        return fh.Span(
            "Error: Recipe name is required and must be text.", cls="text-red-500"
        )
    if not parsed_recipe.ingredients:
        return fh.Span("Error: Missing recipe ingredients.", cls="text-red-500")
    if not parsed_recipe.instructions:
        return fh.Span("Error: Missing recipe instructions.", cls="text-red-500")

    # Build db_data from the parsed Recipe object
    db_data = {
        "name": parsed_recipe.name,
        "ingredients": json.dumps(parsed_recipe.ingredients),
        "instructions": json.dumps(parsed_recipe.instructions),
    }

    try:
        inserted_record = recipes_table.insert(db_data)
        logger.info(
            "Saved recipe via UI: %s, Name: %s",
            inserted_record["id"],
            parsed_recipe.name,  # Log parsed name
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

    current_recipe = _parse_recipe_from_form(form_data)
    original_recipe = _parse_recipe_from_form(form_data, prefix="original_")

    modification_prompt = form_data.get("modification_prompt", "")

    if not modification_prompt:
        error_message = fh.Div(
            "Please enter modification instructions.", cls=f"{CSS_ERROR_CLASS} mt-2"
        )
        mod_prompt_str = (
            modification_prompt if isinstance(modification_prompt, str) else ""
        )
        form_content = _build_edit_review_form(
            current_recipe, original_recipe, mod_prompt_str, error_message
        )
        return form_content.children[0]

    logger.info("Modifying recipe with prompt: %s", modification_prompt)

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

    except Exception as e:
        logger.error(
            "Error during recipe modification for prompt '%s': %s",
            modification_prompt,
            e,
            exc_info=True,
        )
        error_message = fh.Div(
            "Recipe modification failed. An unexpected error occurred.",
            cls=f"{CSS_ERROR_CLASS} mt-2",
        )
        mod_prompt_str = (
            modification_prompt if isinstance(modification_prompt, str) else ""
        )
        form_content = _build_edit_review_form(
            current_recipe, original_recipe, mod_prompt_str, error_message
        )
        return form_content.children[0]

    form_content = _build_edit_review_form(processed_recipe, original_recipe)
    return form_content.children[0]


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
        current_recipe = _parse_recipe_from_form(form_data)
        original_recipe = _parse_recipe_from_form(form_data, prefix="original_")
        logger.debug("Updating diff: Original vs Current")
        # logger.debug(f"Original: {original_recipe.markdown}")
        # logger.debug(f"Current: {current_recipe.markdown}")
        diff_content_wrapper = _build_diff_content(
            original_recipe, current_recipe.markdown
        )
        return diff_content_wrapper
    except Exception as e:
        logger.error("Error updating diff view: %s", e, exc_info=True)
        # Return something innocuous or an error indicator for the diff area
        return fh.Div(
            "Error updating diff", id="diff-content-wrapper", cls="text-red-500"
        )


# --- Main Application Logic Endpoints ---
