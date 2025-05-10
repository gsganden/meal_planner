import difflib
import html
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
from bs4.element import Tag
from fastapi import FastAPI, Request, status
from fasthtml.common import Del, Ins
from httpx import ASGITransport
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError
from starlette import status
from starlette.datastructures import FormData

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

app = fh.FastHTMLWithLiveReload(hdrs=(mu.Theme.blue.headers()))
rt = app.route

api_app = FastAPI()
api_app.include_router(RECIPES_API_ROUTER)

app.mount("/api", api_app)

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
                fh.Li(
                    fh.A(
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
                    hx_target="#recipe_text_container",
                    hx_swap="outerHTML",
                    hx_include="[name='recipe_url']",
                    hx_indicator="#fetch-indicator",
                    cls=mu.ButtonT.primary,
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
            cls="mb-4",
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
            cls=mu.ButtonT.primary,
        ),
        mu.Loading(id="extract-indicator", cls="htmx-indicator ml-2"),
        cls="mt-4",
    )

    disclaimer = fh.P(
        "Recipe extraction uses AI and may not be perfectly accurate. Always "
        "double-check the results.",
        cls=f"{mu.TextT.muted} text-xs mt-1",
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
        cls="space-y-4 mb-6",
    )

    edit_form_target_div = fh.Div(id="edit-form-target", cls="mt-6")
    review_section_target_div = fh.Div(id="review-section-target", cls="mt-6")

    return with_layout(
        mu.Titled(
            "Create Recipe",
            mu.Card(input_section, cls="mt-6"),
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
        return with_layout(
            fh.Div("Error fetching recipes from API.", cls=CSS_ERROR_CLASS)
        )
    except Exception as e:
        logger.error("Error fetching recipes: %s", e, exc_info=True)
        return with_layout(
            fh.Div(
                "An unexpected error occurred while fetching recipes.",
                cls=CSS_ERROR_CLASS,
            )
        )

    if not recipes_data:
        content = fh.Div("No recipes found.")
    else:
        content = fh.Ul(
            *[
                fh.Li(
                    fh.A(
                        recipe["name"],
                        href=f"/recipes/{recipe['id']}",
                        hx_target="#content",
                        hx_push_url="true",
                    )
                )
                for recipe in recipes_data
            ],
            cls="list-disc list-inside",
        )

    return with_layout(mu.Titled("All Recipes", content, id="content"))


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
                mu.Titled(
                    "Recipe Not Found", fh.P("The requested recipe does not exist.")
                )
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
                mu.Titled(
                    "Error",
                    fh.P(
                        "Error fetching recipe from API.",
                        cls=CSS_ERROR_CLASS,
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
            mu.Titled(
                "Error",
                fh.P(
                    "An unexpected error occurred.",
                    cls=CSS_ERROR_CLASS,
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
        fh.H3(recipe_data["name"], cls="text-xl font-bold mb-3"),
        fh.H4("Ingredients", cls="text-lg font-semibold mb-1"),
        fh.Ul(
            *[fh.Li(ing) for ing in recipe_data.get("ingredients", [])],
            cls="list-disc list-inside mb-3",
        ),
    ]
    instructions = recipe_data.get("instructions", [])
    if instructions:
        components.extend(
            [
                fh.H4("Instructions", cls="text-lg font-semibold mb-1"),
                fh.Ul(
                    *[fh.Li(inst) for inst in instructions],
                    cls="list-disc list-inside mb-3",
                ),
            ]
        )

    return fh.Div(
        *components,
        cls="p-4 border rounded bg-gray-100 dark:bg-gray-700 text-sm max-w-none",
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


CSS_ERROR_CLASS = f"{mu.TextT.error} mb-4"


def generate_diff_html(
    before_text: str, after_text: str
) -> tuple[list[str], list[str]]:
    """Generates two lists of strings for diff display."""
    before_lines = before_text.splitlines()
    after_lines = after_text.splitlines()
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines)
    before_items = []
    after_items = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in before_lines[i1:i2]:
                before_items.append(line)
                after_items.append(line)
        elif tag == "replace":
            for line in before_lines[i1:i2]:
                before_items.append(Del(line))
            for line in after_lines[j1:j2]:
                after_items.append(Ins(line))
        elif tag == "delete":
            for line in before_lines[i1:i2]:
                before_items.append(Del(line))
        elif tag == "insert":
            for line in after_lines[j1:j2]:
                after_items.append(Ins(line))

    return before_items, after_items


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


def _build_diff_content_children(
    original_recipe: RecipeBase, current_markdown: str
) -> tuple[fh.FT, fh.FT]:
    """Builds fasthtml.Div components for 'before' and 'after' diff areas."""
    before_items, after_items = generate_diff_html(
        original_recipe.markdown, current_markdown
    )

    pre_style = "white-space: pre-wrap; overflow-wrap: break-word;"
    base_classes = (
        "border p-2 rounded bg-gray-100 dark:bg-gray-700 mt-1 overflow-auto text-xs"
    )

    before_div_component = fh.Div(
        fh.Strong("Initial Extracted Recipe (Reference)"),
        fh.Pre(
            *before_items,
            id="diff-before-pre",
            cls=base_classes,
            style=pre_style,
        ),
        cls="w-1/2",
    )

    after_div_component = fh.Div(
        fh.Strong("Current Edited Recipe"),
        fh.Pre(
            *after_items,
            id="diff-after-pre",
            cls=base_classes,
            style=pre_style,
        ),
        cls="w-1/2",
    )

    return before_div_component, after_div_component


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

    combined_edit_section = fh.Div(
        fh.H2("Edit Recipe", cls="text-3xl mb-4"),
        controls_section,
        editable_section,
    )

    diff_style = fh.Style("""\
        /* Apply background colors, let default text decoration apply */
        ins { @apply bg-green-100 dark:bg-green-700 dark:bg-opacity-40; }\
        del { @apply bg-red-100 dark:bg-red-700 dark:bg-opacity-40; }\
    """)

    main_edit_card = mu.Card(
        mu.Form(
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
    modification_input = mu.Input(
        id="modification_prompt",
        name="modification_prompt",
        placeholder="e.g., Make it vegan, double the servings",
        label="Modify Recipe Request (Optional)",
        value=modification_prompt_value or "",
        cls="mb-2",
    )
    modify_button_container = fh.Div(
        mu.Button(
            "Modify Recipe",
            hx_post="/recipes/modify",
            hx_target="#edit-form-target",
            hx_swap="outerHTML",
            hx_include="closest form",
            hx_indicator="#modify-indicator",
            cls=mu.ButtonT.primary,
        ),
        mu.Loading(id="modify-indicator", cls="htmx-indicator ml-2"),
        cls="mb-4",
    )
    edit_disclaimer = fh.P(
        "AI recipe modification is experimental. Review changes carefully.",
        cls=f"{mu.TextT.muted} text-xs mt-1 mb-4",
    )
    return fh.Div(
        fh.H3("Modify with AI", cls="text-xl mb-2"),
        modification_input,
        modify_button_container,
        edit_disclaimer,
        error_message_content or "",
        cls="mb-6",
    )


def _build_original_hidden_fields(original_recipe: RecipeBase):
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


def _build_editable_section(current_recipe: RecipeBase):
    """Builds the 'Edit Manually' section with inputs for name, ingredients,
    and instructions."""
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
        cls="mb-4",
        hx_post="/recipes/ui/update-diff",
        hx_target="#diff-content-wrapper",
        hx_swap="innerHTML",
        hx_trigger="change, keyup changed delay:500ms",
        hx_include="closest form",
    )


def _render_ingredient_list_items(ingredients: list[str]) -> list[Tag]:
    """Render ingredient input divs as a list of fasthtml.Tag components."""
    items_list = []
    for i, ing_value in enumerate(ingredients):
        input_component = fh.Input(
            type="text",
            name="ingredients",
            value=ing_value,
            placeholder="Ingredient",
            cls="uk-input flex-grow mr-2",
            hx_post="/recipes/ui/update-diff",
            hx_target="#diff-content-wrapper",
            hx_swap="innerHTML",
            hx_trigger="change, keyup changed delay:500ms",
            hx_include="closest form",
        )

        button_component = fh.Button(
            mu.UkIcon("minus-circle", cls=mu.TextT.error),
            type="button",
            hx_post=f"/recipes/ui/delete-ingredient/{i}",
            hx_target="#ingredients-list",
            hx_swap="innerHTML",
            hx_include="closest form",
            cls="uk-button uk-button-danger uk-border-circle p-1 "
            "flex items-center justify-center ml-2",
        )

        item_div = fh.Div(
            input_component,
            button_component,
            cls="flex items-center mb-2",
        )
        items_list.append(item_div)
    return items_list


def _build_ingredients_section(ingredients: list[str]):
    """Builds the ingredients list section with inputs and add/remove buttons."""
    ingredient_item_components = _render_ingredient_list_items(ingredients)

    ingredient_inputs_container = fh.Div(
        *ingredient_item_components,
        id="ingredients-list",
        cls="mb-4",
    )
    add_ingredient_button = mu.Button(
        mu.UkIcon("plus-circle", cls=mu.TextT.primary),
        hx_post="/recipes/ui/add-ingredient",
        hx_target="#ingredients-list",
        hx_swap="innerHTML",
        hx_include="closest form",
        cls="mb-4 uk-border-circle p-1 flex items-center justify-center",
    )
    return fh.Div(
        fh.H3("Ingredients", cls="text-xl mb-2"),
        ingredient_inputs_container,
        add_ingredient_button,
    )


def _render_instruction_list_items(instructions: list[str]) -> list[Tag]:
    """Render instruction textarea divs as a list of fasthtml.Tag components."""
    items_list = []
    for i, inst_value in enumerate(instructions):
        textarea_component = fh.Textarea(
            inst_value,
            name="instructions",
            placeholder="Instruction Step",
            rows=2,
            cls="uk-textarea flex-grow mr-2",
            hx_post="/recipes/ui/update-diff",
            hx_target="#diff-content-wrapper",
            hx_swap="innerHTML",
            hx_trigger="change, keyup changed delay:500ms",
            hx_include="closest form",
        )

        button_component = fh.Button(
            mu.UkIcon("minus-circle", cls=mu.TextT.error),
            type="button",
            hx_post=f"/recipes/ui/delete-instruction/{i}",
            hx_target="#instructions-list",
            hx_swap="innerHTML",
            hx_include="closest form",
            cls="uk-button uk-button-danger uk-border-circle p-1 "
            "flex items-center justify-center ml-2",
        )

        # Align items-start for multiline textarea
        item_div = fh.Div(
            textarea_component,
            button_component,
            cls="flex items-start mb-2",
        )
        items_list.append(item_div)
    return items_list


def _build_instructions_section(instructions: list[str]):
    """Builds the instructions list section with textareas and add/remove buttons."""
    instruction_item_components = _render_instruction_list_items(instructions)

    instruction_inputs_container = fh.Div(
        *instruction_item_components,
        id="instructions-list",
        cls="mb-4",
    )
    add_instruction_button = mu.Button(
        mu.UkIcon("plus-circle", cls=mu.TextT.primary),
        hx_post="/recipes/ui/add-instruction",
        hx_target="#instructions-list",
        hx_swap="innerHTML",
        hx_include="closest form",
        cls="mb-4 uk-border-circle p-1 flex items-center justify-center",
    )
    return fh.Div(
        fh.H3("Instructions", cls="text-xl mb-2"),
        instruction_inputs_container,
        add_instruction_button,
    )


def _build_review_section(original_recipe: RecipeBase, current_recipe: RecipeBase):
    """Builds the 'Review Changes' section with the diff view."""
    before_component, after_component = _build_diff_content_children(
        original_recipe, current_recipe.markdown
    )
    diff_content_wrapper = fh.Div(
        before_component,
        after_component,
        cls="flex space-x-4 mt-4",
        id="diff-content-wrapper",
    )
    save_button_container = _build_save_button(current_recipe)
    return mu.Card(
        fh.Div(
            fh.H2("Review Changes", cls="text-2xl mb-4"),
            diff_content_wrapper,
            save_button_container,
        )
    )


def _build_save_button(recipe: RecipeBase) -> fh.FT:
    """Builds the save button container."""
    return fh.Div(
        mu.Button(
            "Save Recipe",
            hx_post="/recipes/save",
            hx_target="#save-button-container",
            hx_swap="outerHTML",
            hx_include="#edit-review-form",
            hx_indicator="#save-indicator",
            cls=mu.ButtonT.primary,
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

    return fh.Div(
        mu.TextArea(
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
        return fh.Div("No text content provided for extraction.", cls=CSS_ERROR_CLASS)

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
            "Recipe extraction failed. An unexpected error occurred during processing.",
            cls=CSS_ERROR_CLASS,
        )

    if not processed_recipe.ingredients:
        logger.warning(
            "Extraction resulted in empty ingredients. Filling placeholder. Name: %s",
            processed_recipe.name,
        )
        processed_recipe.ingredients = ["No ingredients found"]

    reference_heading = fh.H2("Extracted Recipe (Reference)", cls="text-2xl mb-2 mt-6")
    rendered_content_div = _build_recipe_display(processed_recipe.model_dump())

    rendered_recipe_html = fh.Div(
        reference_heading,
        rendered_content_div,
        cls="mb-6",
    )

    edit_form_card, review_section_card = _build_edit_review_form(
        processed_recipe, processed_recipe
    )

    edit_oob_div = fh.Div(
        edit_form_card,
        hx_swap_oob="innerHTML:#edit-form-target",
    )

    review_oob_div = fh.Div(
        review_section_card,
        hx_swap_oob="innerHTML:#review-section-target",
    )

    return fh.Group(rendered_recipe_html, edit_oob_div, review_oob_div)


@rt("/recipes/save")
async def post_save_recipe(request: Request):
    form_data: FormData = await request.form()
    try:
        parsed_data = _parse_recipe_form_data(form_data)
        recipe_obj = RecipeBase(**parsed_data)
    except ValidationError as e:
        logger.warning("Validation error saving recipe: %s", e, exc_info=False)
        return fh.Span(
            "Invalid recipe data. Please check the fields.",
            cls=CSS_ERROR_CLASS,
            id="save-button-container",
        )
    except Exception as e:
        logger.error("Error parsing form data during save: %s", e, exc_info=True)
        return fh.Span(
            "Error processing form data.",
            cls=CSS_ERROR_CLASS,
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
        return fh.Span(
            user_final_message,
            cls=CSS_ERROR_CLASS,
            id="save-button-container",
        )
    else:
        return fh.Span(
            user_final_message,
            cls=mu.TextT.success,
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
    error_message_content = None
    current_recipe = None
    original_recipe = None
    modification_prompt = ""

    # --- Step 1: Try Parsing ---
    try:
        (
            current_recipe,
            original_recipe,
            modification_prompt,
        ) = _parse_and_validate_modify_form(form_data)  # Raises ModifyFormError

    except ModifyFormError as e:
        # Handle parsing error: try to get original for display
        error_message_content = fh.Div(str(e), cls=f"{CSS_ERROR_CLASS} mt-2")
        try:
            original_data = _parse_recipe_form_data(form_data, prefix="original_")
            original_recipe = RecipeBase(**original_data)  # Use this for display
            if current_recipe is None:
                current_recipe = original_recipe
        except Exception as inner_e:
            logger.error(
                "Could not parse original data on modify error: %s",
                inner_e,
                exc_info=True,
            )
            # Critical failure during error handling
            return fh.Div("Critical error processing form.", cls=CSS_ERROR_CLASS)

    # --- Step 2: Check Prompt (if parsing succeeded) ---
    if error_message_content is None and not modification_prompt:
        logger.info("Modification requested with empty prompt. Returning form.")
        error_message_content = fh.Div(
            "Please enter modification instructions.", cls=f"{CSS_ERROR_CLASS} mt-2"
        )

    # --- Step 3: Try Modification (if parsing succeeded and prompt present) ---
    if error_message_content is None:
        # We should only reach here if parsing succeeded and prompt is present
        # Both current_recipe and original_recipe should be valid RecipeBase objects
        try:
            modified_recipe = await _request_recipe_modification(
                current_recipe, modification_prompt
            )
            # SUCCESS PATH: Build form with modified recipe
            edit_form_card, review_section_card = _build_edit_review_form(
                modified_recipe, original_recipe
            )
            return fh.Group(
                edit_form_card,
                fh.Div(
                    review_section_card, hx_swap_oob="innerHTML:#review-section-target"
                ),
            )

        except RecipeModificationError as e:
            error_message_content = fh.Div(str(e), cls=f"{CSS_ERROR_CLASS} mt-2")
    recipe_to_display = current_recipe if current_recipe else original_recipe
    original_for_display = original_recipe if original_recipe else recipe_to_display

    edit_form_card, review_section_card = _build_edit_review_form(
        recipe_to_display,
        original_for_display,
        modification_prompt,
        error_message_content,
    )
    return fh.Group(
        edit_form_card,
        fh.Div(review_section_card, hx_swap_oob="innerHTML:#review-section-target"),
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


@rt("/recipes/ui/delete-ingredient/{index:int}", methods=["POST"])
async def post_delete_ingredient_row(request: Request, index: int):
    form_data = await request.form()
    try:
        parsed_data = _parse_recipe_form_data(form_data)
        current_ingredients = parsed_data.get("ingredients", [])

        if 0 <= index < len(current_ingredients):
            del current_ingredients[index]
        else:
            logger.warning(f"Attempted to delete ingredient at invalid index {index}")

        parsed_data["ingredients"] = current_ingredients
        new_current_recipe = RecipeBase(**parsed_data)

        original_data = _parse_recipe_form_data(form_data, prefix="original_")
        original_recipe = RecipeBase(**original_data)

        # Regenerate the list of ingredient components
        new_ingredient_item_components = _render_ingredient_list_items(
            new_current_recipe.ingredients
        )
        # Target class for ingredients list (mb-4)
        ingredients_list_component = fh.Div(
            *new_ingredient_item_components,
            id="ingredients-list",
            cls="mb-4",
        )

        # OOB diff wrapper has its own flex/space styling.
        before_notstr, after_notstr = _build_diff_content_children(
            original_recipe, new_current_recipe.markdown
        )
        oob_diff_component = fh.Div(
            before_notstr,
            after_notstr,
            hx_swap_oob="innerHTML:#diff-content-wrapper",
        )

        return ingredients_list_component, oob_diff_component

    except ValidationError as e:
        logger.error(
            f"Validation error processing ingredient deletion at index {index}: {e}",
            exc_info=True,
        )
        # Re-parse form for pre-delete state on validation error
        data_for_error_render = _parse_recipe_form_data(form_data)
        ingredients_for_error_render = data_for_error_render.get("ingredients", [])

        error_items_list = _render_ingredient_list_items(ingredients_for_error_render)
        ingredients_list_component = fh.Div(
            fh.P(
                "Error updating list after delete. Validation failed.",
                cls=CSS_ERROR_CLASS,
            ),
            *error_items_list,
            id="ingredients-list",
            cls="mb-4",
        )
        return ingredients_list_component

    except Exception as e:
        logger.error(f"Error deleting ingredient at index {index}: {e}", exc_info=True)
        return fh.Div(
            "Error processing delete request.",
            cls=CSS_ERROR_CLASS,
            id="ingredients-list",
        )


@rt("/recipes/ui/delete-instruction/{index:int}", methods=["POST"])
async def post_delete_instruction_row(request: Request, index: int):
    form_data = await request.form()
    try:
        parsed_data = _parse_recipe_form_data(form_data)
        current_instructions = parsed_data.get("instructions", [])

        if 0 <= index < len(current_instructions):
            del current_instructions[index]
        else:
            logger.warning(f"Attempted to delete instruction at invalid index {index}")

        parsed_data["instructions"] = current_instructions
        new_current_recipe = RecipeBase(**parsed_data)

        original_data = _parse_recipe_form_data(form_data, prefix="original_")
        original_recipe = RecipeBase(**original_data)

        new_instruction_item_components = _render_instruction_list_items(
            new_current_recipe.instructions
        )
        instructions_list_component = fh.Div(
            *new_instruction_item_components, id="instructions-list", cls="mb-4"
        )

        before_notstr, after_notstr = _build_diff_content_children(
            original_recipe, new_current_recipe.markdown
        )
        oob_diff_component = fh.Div(
            before_notstr, after_notstr, hx_swap_oob="innerHTML:#diff-content-wrapper"
        )

        return instructions_list_component, oob_diff_component

    except ValidationError as e:
        logger.error(
            f"Validation error processing instruction deletion at index {index}: {e}",
            exc_info=True,
        )
        # Re-parse form for pre-delete state on validation error
        data_for_error_render = _parse_recipe_form_data(form_data)
        instructions_for_error_render = data_for_error_render.get("instructions", [])

        error_items_list = _render_instruction_list_items(instructions_for_error_render)
        instructions_list_component = fh.Div(
            fh.P(
                "Error updating list after delete. Validation failed.",
                cls=CSS_ERROR_CLASS,
            ),
            *error_items_list,
            id="instructions-list",
            cls="mb-4",
        )
        return instructions_list_component

    except Exception as e:
        logger.error(f"Error deleting instruction at index {index}: {e}", exc_info=True)
        return fh.Div(
            "Error processing delete request.",
            cls=CSS_ERROR_CLASS,
            id="instructions-list",
        )


@rt("/recipes/ui/add-ingredient", methods=["POST"])
async def post_add_ingredient_row(request: Request):
    form_data = await request.form()
    try:
        parsed_data = _parse_recipe_form_data(form_data)
        current_ingredients = parsed_data.get("ingredients", [])
        current_ingredients.append("")

        parsed_data["ingredients"] = current_ingredients
        new_current_recipe = RecipeBase(**parsed_data)

        original_data = _parse_recipe_form_data(form_data, prefix="original_")
        original_recipe = RecipeBase(**original_data)

        new_ingredient_item_components = _render_ingredient_list_items(
            new_current_recipe.ingredients
        )
        ingredients_list_component = fh.Div(
            *new_ingredient_item_components,
            id="ingredients-list",
            cls="mb-4",
        )

        before_notstr, after_notstr = _build_diff_content_children(
            original_recipe, new_current_recipe.markdown
        )
        oob_diff_component = fh.Div(
            before_notstr, after_notstr, hx_swap_oob="innerHTML:#diff-content-wrapper"
        )

        return ingredients_list_component, oob_diff_component

    except ValidationError as e:
        logger.error(
            f"Validation error processing ingredient addition: {e}", exc_info=True
        )
        current_ingredients_before_error = _parse_recipe_form_data(form_data).get(
            "ingredients", []
        )
        error_items = _render_ingredient_list_items(current_ingredients_before_error)
        return fh.Div(
            fh.P("Error updating list after add.", cls=CSS_ERROR_CLASS),
            *error_items,
            id="ingredients-list",
            cls="mb-4",
        )
    except Exception as e:
        logger.error(f"Error adding ingredient: {e}", exc_info=True)
        return fh.Div(
            "Error processing add request.", cls=CSS_ERROR_CLASS, id="ingredients-list"
        )


@rt("/recipes/ui/add-instruction", methods=["POST"])
async def post_add_instruction_row(request: Request):
    form_data = await request.form()
    try:
        parsed_data = _parse_recipe_form_data(form_data)
        current_instructions = parsed_data.get("instructions", [])
        current_instructions.append("")

        parsed_data["instructions"] = current_instructions
        new_current_recipe = RecipeBase(**parsed_data)

        original_data = _parse_recipe_form_data(form_data, prefix="original_")
        original_recipe = RecipeBase(**original_data)

        new_instruction_item_components = _render_instruction_list_items(
            new_current_recipe.instructions
        )
        instructions_list_component = fh.Div(
            *new_instruction_item_components, id="instructions-list", cls="mb-4"
        )

        before_notstr, after_notstr = _build_diff_content_children(
            original_recipe, new_current_recipe.markdown
        )
        oob_diff_component = fh.Div(
            before_notstr, after_notstr, hx_swap_oob="innerHTML:#diff-content-wrapper"
        )

        return instructions_list_component, oob_diff_component

    except ValidationError as e:
        logger.error(
            f"Validation error processing instruction addition: {e}", exc_info=True
        )
        current_instructions_before_error = _parse_recipe_form_data(form_data).get(
            "instructions", []
        )
        error_items = _render_instruction_list_items(current_instructions_before_error)
        return fh.Div(
            fh.P("Error updating list after add.", cls=CSS_ERROR_CLASS),
            *error_items,
            id="instructions-list",
            cls="mb-4",
        )
    except Exception as e:
        logger.error(f"Error adding instruction: {e}", exc_info=True)
        return fh.Div(
            "Error processing add request.", cls=CSS_ERROR_CLASS, id="instructions-list"
        )


@rt("/recipes/ui/update-diff", methods=["POST"])
async def update_diff(request: Request) -> fh.FT:
    """Updates the diff view based on current form data."""
    form_data = await request.form()
    try:
        current_data = _parse_recipe_form_data(form_data)
        original_data = _parse_recipe_form_data(form_data, prefix="original_")
        current_recipe = RecipeBase(**current_data)
        original_recipe = RecipeBase(**original_data)

        before_component, after_component = _build_diff_content_children(
            original_recipe, current_recipe.markdown
        )
        return fh.Div(
            before_component,
            after_component,
            cls="flex space-x-4 mt-4",
            id="diff-content-wrapper",
        )
    except ValidationError as e:
        logger.warning("Validation error during diff update: %s", e, exc_info=False)
        error_message = "Recipe state invalid for diff. Please check all fields."
        return fh.Div(error_message, cls=CSS_ERROR_CLASS)
    except Exception as e:
        logger.error("Error updating diff: %s", e, exc_info=True)
        return fh.Div("Error updating diff view.", cls=CSS_ERROR_CLASS)
