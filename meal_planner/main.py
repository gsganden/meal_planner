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
    url_input_component = fh.Div(
        fh.Label("Recipe URL (Optional)", cls="block mb-1 text-sm font-medium"),
        fh.Div(
            mu.Input(
                id="recipe_url",
                name="recipe_url",
                type="url",
                placeholder="https://example.com/recipe",
                cls="flex-grow mr-2",
            ),
            fh.Div(
                mu.Button(
                    "Fetch Text from URL",
                    hx_post="/recipes/fetch-text",
                    hx_target="#recipe_text",
                    hx_swap="outerHTML",
                    hx_include="[name='recipe_url']",
                    hx_indicator="#fetch-indicator",
                ),
                mu.Loading(id="fetch-indicator", cls="htmx-indicator ml-2"),
                cls="flex items-center",
            ),
            cls="flex items-end",
        ),
        cls="mb-4",
    )

    text_area = mu.TextArea(
        id="recipe_text",
        name="recipe_text",
        placeholder="Paste full recipe text here, or fetch from URL above.",
        rows=15,
        label="Recipe Text (Editable)",
        cls="mb-4",
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

    input_section = fh.Div(
        fh.H2("Input", cls="text-3xl mb-4 mt-6"),
        fh.P(
            "Enter a URL to fetch recipe text, or paste the recipe text "
            "directly into the text area below.",
            cls="text-sm text-gray-600 mb-4",
        ),
        url_input_component,
        text_area,
        extract_button_group,
        cls="space-y-4 mb-6",
    )

    disclaimer = fh.P(
        "Recipe extraction uses AI and may not be perfectly accurate. Always "
        "double-check the results.",
        cls="text-xs text-gray-500 mt-1 mb-4",
    )
    results_div = fh.Div(id="recipe-results")

    return with_layout(
        mu.Titled(
            "Create Recipe",
            fh.Div(input_section, disclaimer, results_div),
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
    ingredients = [ing for ing in ingredients_values if isinstance(ing, str)]

    instructions_values = form_data.getlist(f"{prefix}instructions")
    instructions = [inst for inst in instructions_values if isinstance(inst, str)]

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
        fh.Strong("Original Recipe"),
        fh.Pre(
            fh.Html(fh.NotStr(before_html)),
            cls="border p-2 rounded bg-gray-50 mt-1 overflow-auto",
            id="diff-before-pre",
            style=pre_style,
        ),
        cls="w-1/2",
    )
    after_area = fh.Div(
        fh.Strong("Current Recipe"),
        fh.Pre(
            fh.Html(fh.NotStr(after_html)),
            cls="border p-2 rounded bg-gray-50 mt-1 overflow-auto",
            id="diff-after-pre",
            style=pre_style,
        ),
        cls="w-1/2",
    )
    return fh.Div(before_area, after_area, cls="flex space-x-4 mt-4")


def _build_edit_review_form(
    current_recipe: Recipe,
    original_recipe: Recipe | None = None,
    modification_prompt_value: str | None = None,
    error_message_content=None,
):
    """Builds the simplified modification and review form."""

    modification_input = mu.Input(
        id="modification_prompt",
        name="modification_prompt",
        placeholder="Enter modification instructions",
        label="Modify Recipe Request",
        value=modification_prompt_value or "",
    )
    modify_button_container = _create_button_with_indicator(
        label="Modify Recipe",
        hx_post="/recipes/modify",
        hx_target="#edit-review-form",
        indicator_id="modify-indicator",
        include_selector="closest form",
        container_id="modify-button-container",
        extra_classes="mb-4",
    )
    edit_disclaimer = fh.P(
        "AI recipe modification is experimental. Always review changes carefully "
        "and ensure the final recipe is safe and suitable for your needs.",
        cls="text-xs text-gray-500 mt-1 mb-4",
    )
    controls_section = fh.Div(
        modification_input,
        modify_button_container,
        edit_disclaimer,
        error_message_content or "",
        cls="mb-6",
    )

    diff_content = fh.Div("Recipe will appear here after extraction.")
    if original_recipe:
        diff_content = _build_diff_content(original_recipe, current_recipe.markdown)
    diff_view_container = fh.Div(diff_content, id="diff-view-container")

    save_modified_button_container = _create_button_with_indicator(
        label="Save Current Recipe",
        hx_post="/recipes/save",
        hx_target="#save-modified-button-container",
        indicator_id="save-indicator",
        include_selector="closest form",
        container_id="save-modified-button-container",
        extra_classes="mt-4",
    )

    diff_style = None
    original_hidden_fields = ()
    if original_recipe:
        diff_style = fh.Style("""
            ins { background-color: #e6ffe6; text-decoration: none; }
            del { background-color: #ffe6e6; text-decoration: none; }
        """)
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

    current_hidden_fields = (
        fh.Input(type="hidden", name="name", value=current_recipe.name),
        *(
            fh.Input(type="hidden", name="ingredients", value=ing)
            for ing in current_recipe.ingredients
        ),
        *(
            fh.Input(type="hidden", name="instructions", value=inst)
            for inst in current_recipe.instructions
        ),
    )

    return fh.Div(
        mu.Form(
            fh.H2("Edit", cls="text-2xl mb-2 mt-6"),
            controls_section,
            diff_view_container,
            save_modified_button_container,
            current_hidden_fields,
            original_hidden_fields,
            id="edit-review-form",
        ),
        diff_style or "",
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

    return _build_edit_review_form(processed_recipe, processed_recipe)


@rt("/recipes/save")
async def post_save_recipe(request: Request):
    form_data: FormData = await request.form()

    if not form_data.get("name") or not isinstance(form_data.get("name"), str):
        return fh.Span(
            "Error: Recipe name is required and must be text.", cls="text-red-500"
        )
    if not form_data.getlist("ingredients"):
        return fh.Span("Error: Missing recipe ingredients.", cls="text-red-500")
    if not form_data.getlist("instructions"):
        return fh.Span("Error: Missing recipe instructions.", cls="text-red-500")

    db_data = {
        "name": form_data.get("name"),
        "ingredients": json.dumps(form_data.getlist("ingredients")),
        "instructions": json.dumps(form_data.getlist("instructions")),
    }

    try:
        inserted_record = recipes_table.insert(db_data)
        logger.info(
            "Saved recipe via UI: %s, Name: %s",
            inserted_record["id"],
            form_data.get("name"),
        )
    except Exception as e:
        logger.error("Database error saving recipe via UI: %s", e, exc_info=True)
        return fh.Span(
            "Error saving recipe.",
            cls=CSS_ERROR_CLASS,
            id="save-modified-button-container",
        )

    return fh.Span(
        "Modified Recipe Saved!",
        cls="text-green-500",
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
