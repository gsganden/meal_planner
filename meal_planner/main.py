import difflib
import html
import logging
import os
import re
from pathlib import Path
from typing import TypeVar

import html2text
import httpx
import instructor
from fastapi import FastAPI, Request, Response, status
from fasthtml.common import *
from httpx import ASGITransport
from monsterui.all import *
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError
from starlette import status
from starlette.datastructures import FormData
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles

from meal_planner.api.recipes import API_ROUTER as RECIPES_API_ROUTER
from meal_planner.models import RecipeBase

MODEL_NAME = "gemini-2.0-flash"
ACTIVE_RECIPE_EXTRACTION_PROMPT_FILE = "20250505_213551__terminal_periods_wording.txt"
ACTIVE_RECIPE_MODIFICATION_PROMPT_FILE = "20250429_183353__initial.txt"

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

app = FastHTMLWithLiveReload(hdrs=(Theme.blue.headers()))
rt = app.route

api_app = FastAPI()
api_app.include_router(RECIPES_API_ROUTER)

app.mount("/api", api_app)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

internal_client = httpx.AsyncClient(
    transport=ASGITransport(app=app),
    base_url="http://internal",  # arbitrary
)


def create_html_cleaner() -> html2text.HTML2Text:
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.body_width = 0
    return h


HTML_CLEANER = create_html_cleaner()


@rt("/")
def get():
    return with_layout(Titled("Meal Planner"))


def sidebar():
    nav = NavContainer(
        Li(
            A(
                DivFullySpaced("Meal Planner"),
                href="/",
                hx_target="#content",
                hx_push_url="true",
            )
        ),
        NavParentLi(
            A(DivFullySpaced("Recipes")),
            NavContainer(
                Li(
                    A(
                        "Create",
                        href="/recipes/extract",
                        hx_target="#content",
                        hx_push_url="true",
                    )
                ),
                Li(
                    A(
                        "View All",
                        href="/recipes",
                        hx_target="#content",
                        hx_push_url="true",
                    )
                ),
                parent=False,
            ),
        ),
        uk_nav=True,
        cls=NavT.primary,
        uk_sticky="offset: 20",
    )
    return Div(nav, cls="space-y-4 p-4 w-full md:w-full")


def with_layout(content):
    indicator_style = Style("""
        .htmx-indicator { opacity: 0; transition: opacity 200ms ease-in; }
        .htmx-indicator.htmx-request { opacity: 1; }
    """)

    hamburger_button = Div(
        Button(
            UkIcon("menu"),
            data_uk_toggle="target: #mobile-sidebar",
            cls="p-2",
        ),
        cls="md:hidden flex justify-end p-2",
    )

    mobile_sidebar_container = Div(
        sidebar(),
        id="mobile-sidebar",
        hidden=True,
    )

    return (
        Title("Meal Planner"),
        indicator_style,
        hamburger_button,
        mobile_sidebar_container,
        Div(cls="flex flex-col md:flex-row w-full")(
            Div(sidebar(), cls="hidden md:block w-1/5 max-w-52"),
            Div(content, cls="md:w-4/5 w-full p-4", id="content"),
        ),
        Script(src="/static/main.js"),
        Script(src="/static/recipe-editor.js"),
    )


@rt("/recipes/extract")
def get():
    url_input_component = Div(
        Div(
            Input(
                id="recipe_url",
                name="recipe_url",
                type="url",
                placeholder="https://example.com/recipe",
                cls="flex-grow mr-2",
            ),
            Div(
                Button(
                    "Fetch Text from URL",
                    hx_post="/recipes/fetch-text",
                    hx_target="#recipe_text_container",
                    hx_swap="outerHTML",
                    hx_include="[name='recipe_url']",
                    hx_indicator="#fetch-indicator",
                    cls=ButtonT.primary,
                ),
                Loading(id="fetch-indicator", cls="htmx-indicator ml-2"),
                cls="flex items-center",
            ),
            cls="flex items-end",
        ),
        cls="mb-4",
    )

    text_area_container = Div(
        TextArea(
            id="recipe_text",
            name="recipe_text",
            placeholder="Paste full recipe text here, or fetch from URL above.",
            rows=15,
            cls="mb-4",
        ),
        id="recipe_text_container",
    )

    extract_button_group = Div(
        Button(
            "Extract Recipe",
            hx_post="/recipes/extract/run",
            hx_target="#recipe-results",
            hx_swap="innerHTML",
            hx_include="#recipe_text_container",
            hx_indicator="#extract-indicator",
            cls=ButtonT.primary,
        ),
        Loading(id="extract-indicator", cls="htmx-indicator ml-2"),
        cls="mt-4",
    )

    disclaimer = P(
        "Recipe extraction uses AI and may not be perfectly accurate. Always "
        "double-check the results.",
        cls=TextT.muted,
    )

    results_div = Div(id="recipe-results")

    input_section = Div(
        H2("Extract Recipe"),
        H3("URL"),
        url_input_component,
        H3("Text"),
        text_area_container,
        extract_button_group,
        disclaimer,
        results_div,
        cls="space-y-4 mb-6",
    )

    edit_form_target_div = Div(id="edit-form-target", cls="mt-6")
    review_section_target_div = Div(id="review-section-target", cls="mt-6")

    return with_layout(
        Titled(
            "Create Recipe",
            Card(input_section, cls="mt-6 mb-6"),
            edit_form_target_div,
            review_section_target_div,
            id="content",
        )
    )


@rt("/recipes")
async def get_recipes_htmx():
    try:
        response = await internal_client.get("/api/v0/recipes")
        response.raise_for_status()
        recipes_data = response.json()
    except httpx.HTTPStatusError as e:
        logger.error(
            "API error fetching recipes: %s Response: %s",
            e,
            e.response.text,
            exc_info=True,
        )
        return with_layout(Div("Error fetching recipes from API.", cls=TextT.error))
    except Exception as e:
        logger.error("Error fetching recipes: %s", e, exc_info=True)
        return with_layout(
            Div(
                "An unexpected error occurred while fetching recipes.",
                cls=TextT.error,
            )
        )

    if not recipes_data:
        content = Div("No recipes found.")
    else:
        content = Ul(
            *[
                Li(
                    A(
                        recipe["name"],
                        href=f"/recipes/{recipe['id']}",
                        hx_target="#content",
                        hx_push_url="true",
                    )
                )
                for recipe in recipes_data
            ],
            cls=ListT.disc,
        )

    return with_layout(Titled("All Recipes", content, id="content"))


@rt("/recipes/{recipe_id:int}")
async def get_single_recipe_page(recipe_id: int):
    """Displays a single recipe page."""
    try:
        response = await internal_client.get(f"/api/v0/recipes/{recipe_id}")
        response.raise_for_status()
        recipe_data = response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning("Recipe ID %s not found when loading page.", recipe_id)
            return with_layout(
                Titled("Recipe Not Found", P("The requested recipe does not exist."))
            )
        else:
            logger.error(
                "API error fetching recipe ID %s: Status %s, Response: %s",
                recipe_id,
                e.response.status_code,
                e.response.text,
                exc_info=True,
            )
            return with_layout(
                Titled(
                    "Error",
                    P(
                        "Error fetching recipe from API.",
                        cls=TextT.error,
                    ),
                )
            )
    except Exception as e:
        logger.error(
            "Unexpected error fetching recipe ID %s for page: %s",
            recipe_id,
            e,
            exc_info=True,
        )
        return with_layout(
            Titled(
                "Error",
                P(
                    "An unexpected error occurred.",
                    cls=TextT.error,
                ),
            )
        )

    content = _build_recipe_display(recipe_data)

    return with_layout(content)


def _build_recipe_display(recipe_data: dict):
    """Builds a Div containing the formatted recipe details.

    Args:
        recipe_data: A dictionary containing 'name', 'ingredients', 'instructions'.

    Returns:
        A fasthtml.Div component ready for display.
    """
    components = [
        H3(recipe_data.get("name", "Untitled Recipe")),
        H4("Ingredients"),
        Ul(
            *[Li(str(ing)) for ing in recipe_data.get("ingredients", [])],
            cls=ListT.bullet,
        ),
    ]
    instructions_list = recipe_data.get("instructions", [])
    if instructions_list:
        components.extend(
            [
                H4("Instructions"),
                Ul(
                    *[Li(str(inst)) for inst in instructions_list],
                    cls=ListT.bullet,
                ),
            ]
        )

    # Restore full Div structure, ensuring id is passed directly
    return Card(
        *components,
        cls=CardT.secondary,
        id="recipe-display-wrapper",
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


T = TypeVar("T", bound=BaseModel)


async def get_structured_llm_response(prompt: str, response_model: type[T]) -> T:
    logger.info(
        "LLM Call Start: model=%s, response_model=%s",
        MODEL_NAME,
        response_model.__name__,
    )
    logger.debug("LLM Prompt:\n%s", prompt)
    try:
        response = await aclient.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "user", "content": prompt},
            ],
            response_model=response_model,
        )
        logger.info(
            "LLM Call Success: model=%s, response_model=%s",
            MODEL_NAME,
            response_model.__name__,
        )
        logger.debug("LLM Parsed Object: %r", response)
        return response
    except Exception as e:
        logger.error(
            "LLM Call Error: model=%s, response_model=%s, error=%s",
            MODEL_NAME,
            response_model.__name__,
            e,
            exc_info=True,
        )
        raise


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

    try:
        page_text = HTML_CLEANER.handle(raw_text)
        logger.info("Cleaned HTML text from: %s", recipe_url)
        return page_text
    except Exception as e:
        logger.error(
            "Error cleaning HTML text from %s: %s", recipe_url, e, exc_info=True
        )
        raise RuntimeError(f"Failed to process URL content: {recipe_url}") from e


async def extract_recipe_from_text(page_text: str) -> RecipeBase:
    """Extracts and post-processes a recipe from text."""
    logger.info("Starting recipe extraction from text:\n%s", page_text)
    try:
        prompt_file_path = _get_prompt_path(
            "recipe_extraction", ACTIVE_RECIPE_EXTRACTION_PROMPT_FILE
        )
        logger.info("Using extraction prompt file: %s", prompt_file_path.name)
        prompt_text = prompt_file_path.read_text().format(page_text=page_text)

        extracted_recipe: RecipeBase = await get_structured_llm_response(
            prompt=prompt_text,
            response_model=RecipeBase,
        )
    except Exception as e:
        logger.error(
            "Error during recipe extraction call: %s", MODEL_NAME, e, exc_info=True
        )
        raise
    processed_recipe = postprocess_recipe(extracted_recipe)
    logger.info(
        "Extraction and postprocessing successful. Recipe Name: %s",
        processed_recipe.name,
    )
    logger.debug("Processed Recipe Object: %r", processed_recipe)
    return processed_recipe


def _get_prompt_path(category: str, filename: str) -> Path:
    """Constructs the full path to a prompt file."""
    return PROMPT_DIR / category / filename


async def extract_recipe_from_url(recipe_url: str) -> RecipeBase:
    """Fetches text from a URL and extracts a recipe from it."""
    return await extract_recipe_from_text(
        await fetch_and_clean_text_from_url(recipe_url)
    )


def postprocess_recipe(recipe: RecipeBase) -> RecipeBase:
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


def _build_diff_content(original_recipe: RecipeBase, current_markdown: str):
    """Builds the inner content for the diff view container."""
    before_html, after_html = generate_diff_html(
        original_recipe.markdown, current_markdown
    )
    pre_style = "white-space: pre-wrap; overflow-wrap: break-word;"

    before_area = Card(
        Strong("Initial Extracted Recipe (Reference)"),
        Pre(
            Html(NotStr(before_html)),
            cls=(
                "border p-2 rounded bg-gray-100 dark:bg-gray-700 mt-1"
                " overflow-auto text-xs"
            ),
            id="diff-before-pre",
            style=pre_style,
        ),
        cls=CardT.secondary,
    )
    after_area = Card(
        Strong("Current Edited Recipe"),
        Pre(
            Html(NotStr(after_html)),
            cls=(
                "border p-2 rounded bg-gray-100 dark:bg-gray-700 mt-1"
                " overflow-auto text-xs"
            ),
            id="diff-after-pre",
            style=pre_style,
        ),
        cls=CardT.secondary,
    )
    return Div(
        before_area, after_area, cls="flex space-x-4 mt-4", id="diff-content-wrapper"
    )


def _build_edit_review_form(
    current_recipe: RecipeBase,
    original_recipe: RecipeBase | None = None,
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

    combined_edit_section = Div(
        H2("Edit Recipe"),
        controls_section,
        editable_section,
    )

    diff_style = Style("""
        /* Apply background colors, let default text decoration apply */
        ins { @apply bg-green-100 dark:bg-green-700 dark:bg-opacity-40; }
        del { @apply bg-red-100 dark:bg-red-700 dark:bg-opacity-40; }
    """)

    main_edit_card = Card(
        Form(
            combined_edit_section,
            *original_hidden_fields,
            id="edit-review-form",
        ),
        diff_style,
    )

    return main_edit_card, review_section


def _build_modification_controls(
    modification_prompt_value: str | None, error_message_content
):
    """Builds the 'Modify with AI' control section."""
    modification_input = Input(
        id="modification_prompt",
        name="modification_prompt",
        placeholder="e.g., Make it vegan, double the servings",
        label="Modify Recipe Request (Optional)",
        value=modification_prompt_value or "",
        cls="mb-2",
    )
    modify_button_container = Div(
        Button(
            "Modify Recipe",
            hx_post="/recipes/modify",
            hx_target="#edit-form-target",
            hx_swap="outerHTML",
            hx_include="closest form",
            hx_indicator="#modify-indicator",
            cls=ButtonT.primary,
        ),
        Loading(id="modify-indicator", cls="htmx-indicator ml-2"),
        cls="mb-4",
    )
    edit_disclaimer = P(
        "AI recipe modification is experimental. Review changes carefully.",
        cls=TextT.muted,
    )
    return Div(
        H3("Modify with AI"),
        modification_input,
        modify_button_container,
        edit_disclaimer,
        error_message_content or "",
        cls="mb-6",
    )


def _build_original_hidden_fields(original_recipe: RecipeBase):
    """Builds the hidden input fields for the original recipe data."""
    return (
        Input(type="hidden", name="original_name", value=original_recipe.name),
        *(
            Input(type="hidden", name="original_ingredients", value=ing)
            for ing in original_recipe.ingredients
        ),
        *(
            Input(type="hidden", name="original_instructions", value=inst)
            for inst in original_recipe.instructions
        ),
    )


def _build_editable_section(current_recipe: RecipeBase):
    """Builds the 'Edit Manually' section with inputs for name, ingredients,
    and instructions."""
    name_input = _build_name_input(current_recipe.name)
    ingredients_section = _build_ingredients_section(current_recipe.ingredients)
    instructions_section = _build_instructions_section(current_recipe.instructions)

    return Div(
        H3("Edit Manually"),
        name_input,
        ingredients_section,
        instructions_section,
    )


def _build_name_input(name_value: str):
    """Builds the input field for the recipe name."""
    return Input(
        id="name",
        name="name",
        label="Recipe Name",
        value=name_value,
        cls="mb-4",
        hx_post="/recipes/ui/update-diff",
        hx_target="#diff-content-wrapper",
        hx_swap="innerHTML",
        hx_trigger="change, keyup changed delay:500ms",
        hx_include="closest form",
    )


def _build_ingredients_section(ingredients: list[str]):
    """Builds the ingredients list section with inputs and add/remove buttons."""
    ingredient_inputs = Div(
        *(_build_ingredient_input(i, ing) for i, ing in enumerate(ingredients)),
        id="ingredients-list",
        cls="mb-4",
        uk_sortable="handle: .drag-handle",
    )
    add_ingredient_button = Button(
        UkIcon("plus-circle", cls=TextT.primary),
        hx_post="/recipes/ui/add-ingredient",
        hx_target="#ingredients-list",
        hx_swap="beforeend",
        cls="mb-4 uk-border-circle p-1 flex items-center justify-center",
    )
    return Div(
        H3("Ingredients"),
        ingredient_inputs,
        add_ingredient_button,
    )


def _build_ingredient_input(index: int, value: str):
    """Builds a single ingredient input row."""
    return Div(
        UkIcon(
            "menu", cls="drag-handle mr-2 cursor-grab text-gray-400 hover:text-gray-600"
        ),
        Input(
            name="ingredients",
            value=value,
            placeholder="Ingredient",
            cls="flex-grow mr-2",
            hx_post="/recipes/ui/update-diff",
            hx_target="#diff-content-wrapper",
            hx_swap="innerHTML",
            hx_trigger="change, keyup changed delay:500ms",
            hx_include="closest form",
        ),
        Button(
            UkIcon("minus-circle", cls=TextT.error),
            cls=(
                "ml-2 uk-border-circle p-1 flex"
                " items-center justify-center delete-item-button"
            ),
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
    instruction_inputs = Div(
        *instruction_items,
        id="instructions-list",
        cls="mb-4",
        uk_sortable="handle: .drag-handle",
    )
    add_instruction_button = Button(
        UkIcon("plus-circle", cls=TextT.primary),
        hx_post="/recipes/ui/add-instruction",
        hx_target="#instructions-list",
        hx_swap="beforeend",
        cls="mb-4 uk-border-circle p-1 flex items-center justify-center",
    )
    return Div(
        H3("Instructions"),
        instruction_inputs,
        add_instruction_button,
    )


def _build_instruction_input(index: int, value: str):
    """Builds a single instruction textarea row."""
    return Div(
        UkIcon(
            "menu", cls="drag-handle mr-2 cursor-grab text-gray-400 hover:text-gray-600"
        ),
        TextArea(
            value,
            name="instructions",
            placeholder="Instruction Step",
            rows=2,
            cls="flex-grow mr-2",
            hx_post="/recipes/ui/update-diff",
            hx_target="#diff-content-wrapper",
            hx_swap="innerHTML",
            hx_trigger="change, keyup changed delay:500ms",
            hx_include="closest form",
        ),
        Button(
            UkIcon("minus-circle", cls=TextT.error),
            cls=(
                "ml-2 uk-border-circle p-1 flex"
                " items-center justify-center delete-item-button"
            ),
            type="button",
        ),
        cls="flex items-start mb-2",
        id=f"instruction-{index}",
    )


def _build_review_section(original_recipe: RecipeBase, current_recipe: RecipeBase):
    """Builds the 'Review Changes' section with the diff view."""
    diff_content_wrapper = _build_diff_content(original_recipe, current_recipe.markdown)
    save_button_container = _build_save_button()
    return Card(
        Div(
            H2("Review Changes"),
            diff_content_wrapper,
            save_button_container,
        )
    )


def _build_save_button():
    """Builds the save button container."""
    return Div(
        Button(
            "Save Recipe",
            hx_post="/recipes/save",
            hx_target="#save-button-container",
            hx_swap="outerHTML",
            hx_include="#edit-review-form",
            hx_indicator="#save-indicator",
            cls=ButtonT.primary,
        ),
        Loading(id="save-indicator", cls="htmx-indicator ml-2"),
        id="save-button-container",
        cls="mt-6",
    )


@rt("/recipes/fetch-text")
async def post_fetch_text(recipe_url: str | None = None):
    if not recipe_url:
        logger.error("Fetch text called without URL.")
        return Div("Please provide a Recipe URL to fetch.", cls=TextT.error)

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
        return Div(
            "Error fetching URL. Please check the URL and your connection.",
            cls=TextT.error,
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP Status Error fetching text from %s: %s", recipe_url, e, exc_info=False
        )
        return Div(
            "Error fetching URL: The server returned an error.",
            cls=TextT.error,
        )
    except RuntimeError as e:
        logger.error(
            "Runtime error fetching text from %s: %s", recipe_url, e, exc_info=True
        )
        return Div("Failed to process the content from the URL.", cls=TextT.error)
    except Exception as e:
        logger.error(
            "Unexpected error fetching text from %s: %s", recipe_url, e, exc_info=True
        )
        return Div("Unexpected error fetching text.", cls=TextT.error)

    return Div(
        TextArea(
            cleaned_text,
            id="recipe_text",
            name="recipe_text",
            rows=15,
            placeholder="Paste recipe text here, or fetch from URL above.",
            cls="mb-4",
        ),
        id="recipe_text_container",
    )


@rt("/recipes/extract/run")
async def post(recipe_url: str | None = None, recipe_text: str | None = None):
    if not recipe_text:
        logging.error("Recipe extraction called without text.")
        return Div("No text content provided for extraction.", cls=TextT.error)

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
        return Div(
            "Recipe extraction failed. An unexpected error occurred during processing.",
            cls=TextT.error,
        )

    if not processed_recipe.ingredients:
        logger.warning(
            "Extraction resulted in empty ingredients. Filling placeholder. Name: %s",
            processed_recipe.name,
        )
        processed_recipe.ingredients = ["No ingredients found"]

    reference_heading = H2("Extracted Recipe (Reference)")

    rendered_content_div = _build_recipe_display(processed_recipe.model_dump())

    rendered_recipe_html = Div(
        reference_heading,
        rendered_content_div,
        cls="mb-6 reference-recipe-display",
    )

    # Restore OOB swaps for edit form and review section
    edit_form_card, review_section_card = _build_edit_review_form(
        processed_recipe, processed_recipe
    )
    edit_oob_div = Div(
        edit_form_card,
        hx_swap_oob="innerHTML:#edit-form-target",
    )
    review_oob_div = Div(
        review_section_card,
        hx_swap_oob="innerHTML:#review-section-target",
    )

    return rendered_recipe_html, edit_oob_div, review_oob_div


@rt("/recipes/save")
async def post_save_recipe(request: Request):
    form_data: FormData = await request.form()
    try:
        parsed_data = _parse_recipe_form_data(form_data)
        recipe_obj = RecipeBase(**parsed_data)
    except ValidationError as e:
        logger.warning("Validation error saving recipe: %s", e, exc_info=False)
        return Span(
            "Invalid recipe data. Please check the fields.",
            cls=TextT.error,
            id="save-button-container",
        )
    except Exception as e:
        logger.error("Error parsing form data during save: %s", e, exc_info=True)
        return Span(
            "Error processing form data.",
            cls=TextT.error,
            id="save-button-container",
        )

    user_final_message = ""
    message_is_error = False

    try:
        response = await internal_client.post(
            "/api/v0/recipes", json=recipe_obj.model_dump()
        )
        response.raise_for_status()
        logger.info("Saved recipe via API call from UI, Name: %s", recipe_obj.name)
        user_final_message = "Current Recipe Saved!"

    except httpx.HTTPStatusError as e:
        message_is_error = True
        logger.error(
            "API error saving recipe: Status %s, Response: %s",
            e.response.status_code,
            e.response.text,
            exc_info=True,
        )
        if e.response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
            user_final_message = "Could not save recipe: Invalid data for some fields."
        else:
            user_final_message = (
                "Could not save recipe. Please check input and try again."
            )
        try:
            detail = e.response.json().get("detail")
            if detail:
                logger.debug("API error detail: %s", detail)
        except Exception:
            logger.debug("Failed to parse API error detail: %s", e, exc_info=True)

    except httpx.RequestError as e:
        message_is_error = True
        logger.error("Network error saving recipe: %s", e, exc_info=True)
        user_final_message = (
            "Could not save recipe due to a network issue. Please try again."
        )

    except Exception as e:
        message_is_error = True
        logger.error("Unexpected error saving recipe via API: %s", e, exc_info=True)
        user_final_message = "An unexpected error occurred while saving the recipe."

    if message_is_error:
        return Span(
            user_final_message,
            cls=TextT.error,
            id="save-button-container",
        )
    else:
        return Span(
            user_final_message,
            cls=TextT.success,
            id="save-button-container",
        )


class ModifyFormError(Exception):
    """Custom exception for errors during modification form parsing/validation."""

    pass


class RecipeModificationError(Exception):
    """Custom exception for errors during LLM recipe modification."""

    pass


@rt("/recipes/modify")
async def post_modify_recipe(request: Request):
    form_data: FormData = await request.form()
    error_message = None
    try:
        (
            current_recipe,
            original_recipe,
            modification_prompt,
        ) = _parse_and_validate_modify_form(form_data)
    except ModifyFormError as e:
        try:
            original_data = _parse_recipe_form_data(form_data, prefix="original_")
            original_recipe = RecipeBase(**original_data)
        except Exception as inner_e:
            logger.error(
                "Could not parse original data on modify error: %s",
                inner_e,
                exc_info=True,
            )
            error_content = f"<div class='{TextT.error}'>"
            error_content += "Critical error processing form.</div>"
            return HTMLResponse(content=error_content)

        error_message = Div(str(e), cls=(TextT.error, "mt-2"))
        modification_prompt = str(form_data.get("modification_prompt", ""))
        current_recipe = original_recipe

    if error_message:
        edit_form_card, review_section_card = _build_edit_review_form(
            current_recipe,
            original_recipe,
            modification_prompt,
            error_message,
        )
        return edit_form_card, Div(
            review_section_card, hx_swap_oob="innerHTML:#review-section-target"
        )

    if not modification_prompt:
        logger.info("Modification requested with empty prompt. Returning form.")
        error_message = Div(
            "Please enter modification instructions.", cls=(TextT.error, "mt-2")
        )
        edit_form_card, review_section_card = _build_edit_review_form(
            current_recipe,
            original_recipe,
            "",
            error_message,
        )
        return edit_form_card, Div(
            review_section_card, hx_swap_oob="innerHTML:#review-section-target"
        )

    try:
        modified_recipe = await _request_recipe_modification(
            current_recipe, modification_prompt
        )
        edit_form_card, review_section_card = _build_edit_review_form(
            modified_recipe, original_recipe
        )
        return edit_form_card, Div(
            review_section_card, hx_swap_oob="innerHTML:#review-section-target"
        )

    except RecipeModificationError as e:
        error_message = Div(str(e), cls=(TextT.error, "mt-2"))
        edit_form_card, review_section_card = _build_edit_review_form(
            current_recipe,
            original_recipe,
            modification_prompt,
            error_message,
        )
        return edit_form_card, Div(
            review_section_card, hx_swap_oob="innerHTML:#review-section-target"
        )


def _parse_and_validate_modify_form(
    form_data: FormData,
) -> tuple[RecipeBase, RecipeBase, str]:
    """Parses and validates form data for the modify recipe request.

    Raises:
        ModifyFormError: If validation or parsing fails.
    """
    try:
        current_data = _parse_recipe_form_data(form_data)
        original_data = _parse_recipe_form_data(form_data, prefix="original_")
        modification_prompt = str(form_data.get("modification_prompt", ""))

        original_recipe = RecipeBase(**original_data)
        current_recipe = RecipeBase(**current_data)

        return current_recipe, original_recipe, modification_prompt

    except ValidationError as e:
        logger.warning("Validation error on modify form submit: %s", e, exc_info=False)
        user_message = "Invalid recipe data. Please check the fields."
        raise ModifyFormError(user_message) from e
    except Exception as e:
        logger.error("Error parsing modify form data: %s", e, exc_info=True)
        user_message = "Error processing modification request form."
        raise ModifyFormError(user_message) from e


async def _request_recipe_modification(
    current_recipe: RecipeBase, modification_prompt: str
) -> RecipeBase:
    """Requests recipe modification from LLM.

    Returns:
        The modified Recipe object.

    Raises:
        RecipeModificationError: If the LLM call or postprocessing fails.
    """
    logger.info("Starting recipe modification. Prompt: %s", modification_prompt)
    try:
        prompt_file_path = _get_prompt_path(
            "recipe_modification", ACTIVE_RECIPE_MODIFICATION_PROMPT_FILE
        )
        logger.info("Using modification prompt file: %s", prompt_file_path.name)
        modification_template = prompt_file_path.read_text()
        modification_full_prompt = modification_template.format(
            current_recipe_markdown=current_recipe.markdown,
            modification_prompt=modification_prompt,
        )
        modified_recipe: RecipeBase = await get_structured_llm_response(
            prompt=modification_full_prompt,
            response_model=RecipeBase,
        )
        processed_recipe = postprocess_recipe(modified_recipe)
        logger.info(
            "Modification and postprocessing successful. Recipe Name: %s",
            processed_recipe.name,
        )
        logger.debug("Modified Recipe Object: %r", processed_recipe)
        return processed_recipe

    except Exception as e:
        logger.error(
            "Error during recipe modification for prompt '%s': %s",
            modification_prompt,
            e,
            exc_info=True,
        )
        user_message = "Recipe modification failed. An unexpected error occurred."
        raise RecipeModificationError(user_message) from e


@rt("/recipes/ui/add-ingredient", methods=["POST"])
def post_add_ingredient_row():
    return Div(
        UkIcon(
            "menu", cls="drag-handle mr-2 cursor-grab text-gray-400 hover:text-gray-600"
        ),
        Input(
            name="ingredients",
            value="",
            placeholder="New Ingredient",
            cls="flex-grow mr-2",
            hx_post="/recipes/ui/update-diff",
            hx_target="#diff-content-wrapper",
            hx_swap="innerHTML",
            hx_trigger="change, keyup changed delay:500ms",
            hx_include="closest form",
        ),
        Button(
            UkIcon("minus-circle", cls=TextT.error),
            cls=(
                "ml-2 uk-border-circle p-1 flex"
                " items-center justify-center delete-item-button"
            ),
            type="button",
        ),
        cls="flex items-center mb-2",
    )


@rt("/recipes/ui/add-instruction", methods=["POST"])
def post_add_instruction_row():
    return Div(
        UkIcon(
            "menu", cls="drag-handle mr-2 cursor-grab text-gray-400 hover:text-gray-600"
        ),
        TextArea(
            "",
            name="instructions",
            placeholder="New Instruction Step",
            rows=2,
            cls="flex-grow mr-2",
            hx_post="/recipes/ui/update-diff",
            hx_target="#diff-content-wrapper",
            hx_swap="innerHTML",
            hx_trigger="change, keyup changed delay:500ms",
            hx_include="closest form",
        ),
        Button(
            UkIcon("minus-circle", cls=TextT.error),
            cls=(
                "ml-2 uk-border-circle p-1 flex"
                " items-center justify-center delete-item-button"
            ),
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
    return Input(
        id="name",
        name="name",
        label="Recipe Name",
        value=name_value,
        cls="mb-4",
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

        original_recipe = RecipeBase(**original_data)
        current_recipe = RecipeBase(**current_data)

    except ValidationError as e:
        logger.debug(
            "Validation error during diff update (expected during edit): %s", e
        )
        return Div(
            "Recipe state invalid for diff",
            id="diff-content-wrapper",
            cls=TextT.error,
        )
    except Exception as e:
        logger.error("Error preparing data for diff view: %s", e, exc_info=True)
        return Div(
            "Error preparing data for diff",
            id="diff-content-wrapper",
            cls=TextT.error,
        )

    try:
        logger.debug("Updating diff: Original vs Current")
        diff_content_wrapper = _build_diff_content(
            original_recipe, current_recipe.markdown
        )
        return diff_content_wrapper
    except Exception as e:
        logger.error("Error generating diff view: %s", e, exc_info=True)
        return Div(
            "Error generating diff view",
            id="diff-content-wrapper",
            cls=TextT.error,
        )
