import difflib
import logging
from pathlib import Path

import httpx
from bs4.element import Tag
from fastapi import FastAPI, Request, status
from fasthtml.common import *
from httpx import ASGITransport
from monsterui.all import *
from pydantic import ValidationError
from starlette import status
from starlette.datastructures import FormData
from starlette.staticfiles import StaticFiles

from meal_planner.api.recipes import API_ROUTER as RECIPES_API_ROUTER
from meal_planner.models import RecipeBase
from meal_planner.services.llm_service import (
    generate_modified_recipe as llm_generate_modified_recipe,
)
from meal_planner.services.llm_service import (
    generate_recipe_from_text as llm_generate_recipe_from_text,
)
from meal_planner.services.recipe_processing import postprocess_recipe
from meal_planner.services.webpage_text_extractor import (
    fetch_and_clean_text_from_url,
)

MODEL_NAME = "gemini-2.0-flash"

STATIC_DIR = Path(__file__).resolve().parent / "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


app = FastHTMLWithLiveReload(hdrs=(Theme.blue.headers()))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
rt = app.route

api_app = FastAPI()
api_app.include_router(RECIPES_API_ROUTER)

app.mount("/api", api_app)

internal_client = httpx.AsyncClient(
    transport=ASGITransport(app=app),
    base_url="http://internal",  # arbitrary
)

internal_api_client = httpx.AsyncClient(
    transport=ASGITransport(app=api_app),
    base_url="http://internal-api",  # arbitrary
)

CSS_ERROR_CLASS = str(TextT.error)


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
            Div(
                content,
                cls="md:w-4/5 w-full p-4",
                id="content",
                hx_trigger="recipeListChanged from:body",
                hx_get="/recipes",
                hx_target="#recipe-list-area",
                hx_swap="outerHTML",
            ),
        ),
        Script(src="/static/recipe-editor.js"),
    )


@rt("/recipes/extract")
def get():
    url_input_component = Div(
        Div(
            Input(
                id="input_url",
                name="input_url",
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
                    hx_include="[name='input_url']",
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
        cls=f"{TextT.muted} text-xs mt-1",
    )

    results_div = Div(id="recipe-results")

    input_section = Div(
        H2("Extract Recipe"),
        H3("URL"),
        url_input_component,
        Div(id="fetch-url-error-display", cls="mt-2 mb-2"),
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
            Card(input_section, cls="mt-6"),
            edit_form_target_div,
            review_section_target_div,
            id="content",
        )
    )


@rt("/recipes")
async def get_recipes_htmx(request: Request):
    recipes_data = []
    error_content = None
    try:
        response = await internal_api_client.get("/v0/recipes")
        response.raise_for_status()
        recipes_data = response.json()
    except httpx.HTTPStatusError as e:
        logger.error(
            "API error fetching recipes: %s Response: %s",
            e,
            e.response.text,
            exc_info=True,
        )
        error_class = getattr(TextT, "error", "uk-text-danger")
        error_content = Titled(
            "Error",
            Div("Error fetching recipes from API.", cls=f"{error_class} mb-4"),
            id="recipe-list-area",
        )
    except Exception as e:
        logger.error("Error fetching recipes: %s", e, exc_info=True)
        error_class = getattr(TextT, "error", "uk-text-danger")
        error_content = Titled(
            "Error",
            Div(
                "An unexpected error occurred while fetching recipes.",
                cls=f"{error_class} mb-4",
            ),
            id="recipe-list-area",
        )

    if error_content:
        if "HX-Request" in request.headers:
            return error_content
        else:
            return with_layout(error_content)

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
                        cls="mr-2",
                    ),
                    Button(
                        UkIcon("minus-circle", cls=CSS_ERROR_CLASS),
                        title="Delete",
                        hx_delete=f"/api/v0/recipes/{recipe['id']}",
                        hx_confirm=f"Are you sure you want to delete {recipe['name']}?",
                        cls=f"{ButtonT.sm} p-1",
                    ),
                    id=f"recipe-item-{recipe['id']}",
                    cls="flex items-center justify-start gap-x-2 mb-1",
                )
                for recipe in recipes_data
            ],
            id="recipe-list-ul",
        )

    list_component = Titled("All Recipes", content, id="recipe-list-area")

    if "HX-Request" in request.headers:
        return list_component
    else:
        return with_layout(list_component)


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
            Titled(
                "Error",
                P(
                    "An unexpected error occurred.",
                    cls=CSS_ERROR_CLASS,
                ),
            )
        )

    content = _build_recipe_display(recipe_data)

    return with_layout(content)


def _build_recipe_display(recipe_data: dict):
    """Builds a Card containing the formatted recipe details.

    Args:
        recipe_data: A dictionary containing 'name', 'ingredients', 'instructions'.

    Returns:
        A monsterui.Card component ready for display.
    """
    components = [
        H3(recipe_data["name"]),
        H4("Ingredients"),
        Ul(
            *[Li(ing) for ing in recipe_data.get("ingredients", [])],
            cls=ListT.bullet,
        ),
    ]
    instructions = recipe_data.get("instructions", [])
    if instructions:
        components.extend(
            [
                H4("Instructions"),
                Ul(
                    *[Li(inst) for inst in instructions],
                    cls=ListT.bullet,
                ),
            ]
        )

    return Card(
        *components,
        cls=CardT.secondary,
    )


async def extract_recipe_from_text(page_text: str) -> RecipeBase:
    """Extracts a recipe from the given text using an LLM and postprocesses it."""
    logger.info("Attempting to extract recipe from provided text.")
    try:
        extracted_recipe: RecipeBase = await llm_generate_recipe_from_text(
            text=page_text
        )
    except Exception as e:
        logger.error(
            f"LLM service failed to generate recipe from text: {e!r}", exc_info=True
        )
        raise

    processed_recipe = postprocess_recipe(extracted_recipe)
    logger.info(
        "Extraction (via llm_service) and postprocessing successful. Recipe Name: %s",
        processed_recipe.name,
    )
    logger.debug("Processed Recipe Object: %r", processed_recipe)
    return processed_recipe


async def extract_recipe_from_url(recipe_url: str) -> RecipeBase:
    """Fetches text from a URL, cleans it, and extracts a recipe from it."""
    cleaned_text = await fetch_and_clean_text_from_url(recipe_url)
    return await extract_recipe_from_text(cleaned_text)


def generate_diff_html(
    before_text: str, after_text: str
) -> tuple[list[str | FT], list[str | FT]]:
    """Generates two lists of fasthtml components/strings for diff display."""
    before_lines = before_text.splitlines()
    after_lines = after_text.splitlines()
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines)
    before_items = []
    after_items = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in before_lines[i1:i2]:
                before_items.extend([line, "\n"])
                after_items.extend([line, "\n"])
        elif tag == "replace":
            for line in before_lines[i1:i2]:
                before_items.extend([Del(line), "\n"])
            for line in after_lines[j1:j2]:
                after_items.extend([Ins(line), "\n"])
        elif tag == "delete":
            for line in before_lines[i1:i2]:
                before_items.extend([Del(line), "\n"])
        elif tag == "insert":
            for line in after_lines[j1:j2]:
                after_items.extend([Ins(line), "\n"])

    if before_items and before_items[-1] == "\n":
        before_items.pop()
    if after_items and after_items[-1] == "\n":
        after_items.pop()

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
) -> tuple[FT, FT]:
    """Builds fasthtml.Div components for 'before' and 'after' diff areas."""
    before_items, after_items = generate_diff_html(
        original_recipe.markdown, current_markdown
    )

    pre_style = "white-space: pre-wrap; overflow-wrap: break-word;"
    base_classes = (
        "border p-2 rounded bg-gray-100 dark:bg-gray-700 mt-1 overflow-auto text-xs"
    )

    before_div_component = Card(
        Strong("Initial Extracted Recipe (Reference)"),
        Pre(
            *before_items,
            id="diff-before-pre",
            cls=base_classes,
            style=pre_style,
        ),
        cls=CardT.secondary,
    )

    after_div_component = Card(
        Strong("Current Edited Recipe"),
        Pre(
            *after_items,
            id="diff-after-pre",
            cls=base_classes,
            style=pre_style,
        ),
        cls=CardT.secondary,
    )

    return before_div_component, after_div_component


def _build_edit_review_form(
    current_recipe: RecipeBase,
    original_recipe: RecipeBase | None = None,
    modification_prompt_value: str | None = None,
    error_message_content: FT | None = None,
):
    """Builds the primary recipe editing interface components.

    This function constructs the main card containing the editable recipe form
    (manual edits and AI modification controls) and the separate review card
    containing the diff view and save button.

    Args:
        current_recipe: The RecipeBase object representing the current state
            of the recipe being edited.
        original_recipe: An optional RecipeBase object representing the initial
            state of the recipe before any edits (or modifications). This is used
            as the baseline for the diff view. If None, `current_recipe` is used
            as the baseline.
        modification_prompt_value: An optional string containing the user's
            previous AI modification request, used to pre-fill the input.
        error_message_content: Optional FastHTML content (e.g., a Div with an
            error message) to display within the modification controls section.

    Returns:
        A tuple containing two components:
        1. main_edit_card (Card): The card containing the modification
           controls and the editable fields (name, ingredients, instructions).
        2. review_section_card (Card): The card containing the diff view
           and the save button.
    """
    diff_baseline_recipe = original_recipe
    if diff_baseline_recipe is None:
        diff_baseline_recipe = current_recipe

    controls_section = _build_modification_controls(
        modification_prompt_value, error_message_content
    )
    original_hidden_fields = _build_original_hidden_fields(diff_baseline_recipe)
    editable_section = _build_editable_section(current_recipe)
    review_section = _build_review_section(diff_baseline_recipe, current_recipe)

    combined_edit_section = Div(
        H2("Edit Recipe"),
        Div(
            controls_section,
            editable_section,
            id="form-content-wrapper",
        ),
        cls="space-y-4",
    )

    diff_style = Style("""\
        /* Apply background colors, let default text decoration apply */
        ins { @apply bg-green-100 dark:bg-green-700 dark:bg-opacity-40; }\
        del { @apply bg-red-100 dark:bg-red-700 dark:bg-opacity-40; }\
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
        cls=f"{TextT.muted} text-xs mt-1 mb-4",
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


def _render_ingredient_list_items(ingredients: list[str]) -> list[Tag]:
    """Render ingredient input divs as a list of fasthtml.Tag components."""
    items_list = []
    for i, ing_value in enumerate(ingredients):
        drag_handle_component = UkIcon(
            "menu",
            cls="drag-handle mr-2 cursor-grab text-gray-400 hover:text-gray-600",
        )
        input_component = Input(
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

        button_component = Button(
            UkIcon("minus-circle", cls=CSS_ERROR_CLASS),
            type="button",
            hx_post=f"/recipes/ui/delete-ingredient/{i}",
            hx_target="#ingredients-list",
            hx_swap="innerHTML",
            hx_include="closest form",
            cls="uk-button uk-button-danger uk-border-circle p-1 "
            "flex items-center justify-center ml-2",
        )

        item_div = Div(
            drag_handle_component,
            input_component,
            button_component,
            cls="flex items-center mb-2",
        )
        items_list.append(item_div)
    return items_list


def _build_ingredients_section(ingredients: list[str]):
    """Builds the ingredients list section with inputs and add/remove buttons."""
    ingredient_item_components = _render_ingredient_list_items(ingredients)

    ingredient_inputs_container = Div(
        *ingredient_item_components,
        id="ingredients-list",
        cls="mb-4",
        uk_sortable="handle: .drag-handle",
        hx_trigger="moved",
        hx_post="/recipes/ui/update-diff",
        hx_target="#diff-content-wrapper",
        hx_swap="innerHTML",
        hx_include="closest form",
    )
    add_ingredient_button = Button(
        UkIcon("plus-circle", cls=TextT.primary),
        hx_post="/recipes/ui/add-ingredient",
        hx_target="#ingredients-list",
        hx_swap="innerHTML",
        hx_include="closest form",
        cls="mb-4 uk-border-circle p-1 flex items-center justify-center",
    )
    return Div(
        H3("Ingredients"),
        ingredient_inputs_container,
        add_ingredient_button,
    )


def _render_instruction_list_items(instructions: list[str]) -> list[Tag]:
    """Render instruction textarea divs as a list of fasthtml.Tag components."""
    items_list = []
    for i, inst_value in enumerate(instructions):
        drag_handle_component = UkIcon(
            "menu",
            cls="drag-handle mr-2 cursor-grab text-gray-400 hover:text-gray-600",
        )
        textarea_component = Textarea(
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

        button_component = Button(
            UkIcon("minus-circle", cls=CSS_ERROR_CLASS),
            type="button",
            hx_post=f"/recipes/ui/delete-instruction/{i}",
            hx_target="#instructions-list",
            hx_swap="innerHTML",
            hx_include="closest form",
            cls="uk-button uk-button-danger uk-border-circle p-1 "
            "flex items-center justify-center ml-2",
        )

        item_div = Div(
            drag_handle_component,
            textarea_component,
            button_component,
            cls="flex items-start mb-2",
        )
        items_list.append(item_div)
    return items_list


def _build_instructions_section(instructions: list[str]):
    """Builds the instructions list section with textareas and add/remove buttons."""
    instruction_item_components = _render_instruction_list_items(instructions)

    instruction_inputs_container = Div(
        *instruction_item_components,
        id="instructions-list",
        cls="mb-4",
        uk_sortable="handle: .drag-handle",
        hx_trigger="moved",
        hx_post="/recipes/ui/update-diff",
        hx_target="#diff-content-wrapper",
        hx_swap="innerHTML",
        hx_include="closest form",
    )
    add_instruction_button = Button(
        UkIcon("plus-circle", cls=TextT.primary),
        hx_post="/recipes/ui/add-instruction",
        hx_target="#instructions-list",
        hx_swap="innerHTML",
        hx_include="closest form",
        cls="mb-4 uk-border-circle p-1 flex items-center justify-center",
    )
    return Div(
        H3("Instructions"),
        instruction_inputs_container,
        add_instruction_button,
    )


def _build_review_section(original_recipe: RecipeBase, current_recipe: RecipeBase):
    """Builds the 'Review Changes' section with the diff view."""
    before_component, after_component = _build_diff_content_children(
        original_recipe, current_recipe.markdown
    )
    diff_content_wrapper = Div(
        before_component,
        after_component,
        cls="flex space-x-4 mt-4",
        id="diff-content-wrapper",
    )
    save_button_container = _build_save_button()
    return Card(
        Div(
            H2("Review Changes"),
            diff_content_wrapper,
            save_button_container,
        )
    )


def _build_save_button() -> FT:
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
async def post_fetch_text(input_url: str | None = None):
    def _prepare_error_response(error_message_str: str):
        error_div = Div(
            error_message_str, cls=CSS_ERROR_CLASS, id="fetch-url-error-display"
        )
        error_oob = Div(error_div, hx_swap_oob="outerHTML:#fetch-url-error-display")
        text_area = Div(
            TextArea(
                id="recipe_text",
                name="recipe_text",
                placeholder="Paste full recipe text here, or fetch from URL above.",
                rows=15,
                cls="mb-4",
            ),
            id="recipe_text_container",
        )
        return Group(text_area, error_oob)

    if not input_url:
        logger.error("Fetch text called without URL.")
        return _prepare_error_response("Please provide a Recipe URL to fetch.")

    try:
        logger.info("Fetching and cleaning text from URL: %s", input_url)
        cleaned_text = await fetch_and_clean_text_from_url(input_url)
        text_area = Div(
            TextArea(
                cleaned_text,
                id="recipe_text",
                name="recipe_text",
                placeholder="Paste full recipe text here, or fetch from URL above.",
                rows=15,
                cls="mb-4",
            ),
            id="recipe_text_container",
        )
        clear_error_oob = Div(
            Div(id="fetch-url-error-display"),
            hx_swap_oob="outerHTML:#fetch-url-error-display",
        )
        return Group(text_area, clear_error_oob)
    except httpx.RequestError as e:
        logger.error("Network error fetching URL %s: %s", input_url, e, exc_info=True)
        return _prepare_error_response(
            "Error fetching URL. Please check the URL and your connection."
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP error fetching URL %s: %s. Response: %s",
            input_url,
            e,
            e.response.text,
            exc_info=True,
        )
        return _prepare_error_response(
            "Error fetching URL: The server returned an error."
        )
    except RuntimeError as e:
        logger.error(
            "RuntimeError processing URL content from %s: %s",
            input_url,
            e,
            exc_info=True,
        )
        return _prepare_error_response("Failed to process the content from the URL.")
    except Exception as e:
        logger.error(
            "Unexpected error fetching text from %s: %s", input_url, e, exc_info=True
        )
        return _prepare_error_response(
            "An unexpected error occurred while fetching text."
        )


@rt("/recipes/extract/run")
async def post(recipe_url: str | None = None, recipe_text: str | None = None):
    if not recipe_text:
        logging.error("Recipe extraction called without text.")
        return Div("No text content provided for extraction.", cls=CSS_ERROR_CLASS)

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
            cls=CSS_ERROR_CLASS,
        )

    rendered_recipe_html = Div(
        H2("Extracted Recipe (Reference)"),
        _build_recipe_display(processed_recipe.model_dump()),
        cls="mb-6 space-y-4",
    )

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

    return Group(rendered_recipe_html, edit_oob_div, review_oob_div)


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
            cls=CSS_ERROR_CLASS,
            id="save-button-container",
        )
    except Exception as e:
        logger.error("Error parsing form data during save: %s", e, exc_info=True)
        return Span(
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
        return Span(
            user_final_message,
            cls=CSS_ERROR_CLASS,
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
    form_data = await request.form()
    modification_prompt = str(form_data.get("modification_prompt", ""))

    error_message_for_ui: FT | None = None
    current_data_for_form_render: dict
    original_recipe_for_form_render: RecipeBase

    try:
        (validated_current_recipe, validated_original_recipe, _) = (
            _parse_and_validate_modify_form(form_data)
        )

        current_data_for_form_render = validated_current_recipe.model_dump()
        original_recipe_for_form_render = validated_original_recipe

        if not modification_prompt:
            logger.info("Modification requested with empty prompt.")
            error_message_for_ui = Div(
                "Please enter modification instructions.", cls=f"{CSS_ERROR_CLASS} mt-2"
            )

        else:
            try:
                modified_recipe = await _request_recipe_modification(
                    validated_current_recipe, modification_prompt
                )
                edit_form_card, review_section_card = _build_edit_review_form(
                    current_recipe=modified_recipe,
                    original_recipe=validated_original_recipe,
                    modification_prompt_value=modification_prompt,
                    error_message_content=None,
                )
                oob_review = Div(
                    review_section_card, hx_swap_oob="innerHTML:#review-section-target"
                )
                return Div(
                    edit_form_card, oob_review, id="edit-form-target", cls="mt-6"
                )

            except RecipeModificationError as llm_e:
                logger.error("LLM modification error: %s", llm_e, exc_info=True)
                error_message_for_ui = Div(str(llm_e), cls=f"{CSS_ERROR_CLASS} mt-2")

    except ModifyFormError as form_e:
        logger.warning("Form validation/parsing error: %s", form_e, exc_info=False)
        error_message_for_ui = Div(str(form_e), cls=f"{CSS_ERROR_CLASS} mt-2")
        try:
            original_data_raw = _parse_recipe_form_data(form_data, prefix="original_")
            original_recipe_for_form_render = RecipeBase(**original_data_raw)
            current_data_for_form_render = original_data_raw
        except Exception as parse_orig_e:
            logger.error(
                "Critical: Could not parse original data during ModifyFormError "
                "handling: %s",
                parse_orig_e,
                exc_info=True,
            )
            critical_error_msg = Div(
                "Critical Error: Could not recover the recipe form state. Please "
                "refresh and try again.",
                cls=CSS_ERROR_CLASS,
                id="edit-form-target",
            )
            return critical_error_msg

    except Exception as e:
        logger.error(
            "Unexpected error in recipe modification flow: %s", e, exc_info=True
        )
        critical_error_msg = Div(
            "Critical Error: An unexpected error occurred. Please refresh and try "
            "again.",
            cls=CSS_ERROR_CLASS,
            id="edit-form-target",
        )
        return critical_error_msg

    try:
        current_recipe_for_render = RecipeBase(**current_data_for_form_render)
    except ValidationError:
        logger.error(
            "Data intended for form render failed validation: %s",
            current_data_for_form_render,
        )
        current_recipe_for_render = RecipeBase(
            name="[Validation Error]", ingredients=[], instructions=[]
        )

    edit_form_card, review_section_card = _build_edit_review_form(
        current_recipe=current_recipe_for_render,
        original_recipe=original_recipe_for_form_render,
        modification_prompt_value=modification_prompt,
        error_message_content=error_message_for_ui,
    )
    oob_review = Div(
        review_section_card, hx_swap_oob="innerHTML:#review-section-target"
    )
    return Div(edit_form_card, oob_review, id="edit-form-target", cls="mt-6")


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
    """Requests recipe modification from LLM service and handles postprocessing."""
    logger.info(
        "Requesting recipe modification from llm_service. Current: %s, Prompt: %s",
        current_recipe.name,
        modification_prompt,
    )
    try:
        modified_recipe: RecipeBase = await llm_generate_modified_recipe(
            current_recipe=current_recipe, modification_request=modification_prompt
        )
        processed_recipe = postprocess_recipe(modified_recipe)
        logger.info(
            "Modification (via llm_service) and postprocessing successful. "
            "Recipe Name: %s",
            processed_recipe.name,
        )
        logger.debug("Modified Recipe Object: %r", processed_recipe)
        return processed_recipe
    except Exception as e:
        logger.error(
            "Error calling llm_generate_modified_recipe from "
            "_request_recipe_modification: %s",
            e,
            exc_info=True,
        )
        user_message = (
            "Recipe modification failed. "
            "An unexpected error occurred during service call."
        )
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

        new_ingredient_item_components = _render_ingredient_list_items(
            new_current_recipe.ingredients
        )
        return _build_sortable_list_with_oob_diff(
            list_id="ingredients-list",
            rendered_list_items=new_ingredient_item_components,
            original_recipe=original_recipe,
            current_recipe=new_current_recipe,
        )

    except ValidationError as e:
        logger.error(
            f"Validation error processing ingredient deletion at index {index}: {e}",
            exc_info=True,
        )
        data_for_error_render = _parse_recipe_form_data(form_data)
        ingredients_for_error_render = data_for_error_render.get("ingredients", [])

        error_items_list = _render_ingredient_list_items(ingredients_for_error_render)
        ingredients_list_component = Div(
            P(
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
        return Div(
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
        return _build_sortable_list_with_oob_diff(
            list_id="instructions-list",
            rendered_list_items=new_instruction_item_components,
            original_recipe=original_recipe,
            current_recipe=new_current_recipe,
        )

    except ValidationError as e:
        logger.error(
            f"Validation error processing instruction deletion at index {index}: {e}",
            exc_info=True,
        )
        data_for_error_render = _parse_recipe_form_data(form_data)
        instructions_for_error_render = data_for_error_render.get("instructions", [])

        error_items_list = _render_instruction_list_items(instructions_for_error_render)
        instructions_list_component = Div(
            P(
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
        return Div(
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
        return _build_sortable_list_with_oob_diff(
            list_id="ingredients-list",
            rendered_list_items=new_ingredient_item_components,
            original_recipe=original_recipe,
            current_recipe=new_current_recipe,
        )

    except ValidationError as e:
        logger.error(
            f"Validation error processing ingredient addition: {e}", exc_info=True
        )
        current_ingredients_before_error = _parse_recipe_form_data(form_data).get(
            "ingredients", []
        )
        error_items = _render_ingredient_list_items(current_ingredients_before_error)
        return Div(
            P("Error updating list after add.", cls=CSS_ERROR_CLASS),
            *error_items,
            id="ingredients-list",
            cls="mb-4",
        )
    except Exception as e:
        logger.error(f"Error adding ingredient: {e}", exc_info=True)
        return Div(
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
        return _build_sortable_list_with_oob_diff(
            list_id="instructions-list",
            rendered_list_items=new_instruction_item_components,
            original_recipe=original_recipe,
            current_recipe=new_current_recipe,
        )

    except ValidationError as e:
        logger.error(
            f"Validation error processing instruction addition: {e}", exc_info=True
        )
        current_instructions_before_error = _parse_recipe_form_data(form_data).get(
            "instructions", []
        )
        error_items = _render_instruction_list_items(current_instructions_before_error)
        return Div(
            P("Error updating list after add.", cls=CSS_ERROR_CLASS),
            *error_items,
            id="instructions-list",
            cls="mb-4",
        )
    except Exception as e:
        logger.error(f"Error adding instruction: {e}", exc_info=True)
        return Div(
            "Error processing add request.", cls=CSS_ERROR_CLASS, id="instructions-list"
        )


@rt("/recipes/ui/update-diff", methods=["POST"])
async def update_diff(request: Request) -> FT:
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
        return Div(
            before_component,
            after_component,
            cls="flex space-x-4 mt-4",
            id="diff-content-wrapper",
        )
    except ValidationError as e:
        logger.warning("Validation error during diff update: %s", e, exc_info=False)
        error_message = "Recipe state invalid for diff. Please check all fields."
        return Div(error_message, cls=CSS_ERROR_CLASS)
    except Exception as e:
        logger.error("Error updating diff: %s", e, exc_info=True)
        return Div("Error updating diff view.", cls=CSS_ERROR_CLASS)


def _build_sortable_list_with_oob_diff(
    list_id: str,
    rendered_list_items: list[Tag],
    original_recipe: RecipeBase,
    current_recipe: RecipeBase,
) -> tuple[Div, Div]:
    """
    Builds a sortable list component and an OOB diff component.

    Args:
        list_id: The HTML ID for the list container (e.g., "ingredients-list").
        rendered_list_items: A list of fasthtml.Tag components representing the items.
        original_recipe: The baseline recipe for the diff.
        current_recipe: The current state of the recipe for the diff.

    Returns:
        A tuple containing the list component Div and the OOB diff component Div.
    """
    list_component = Div(
        *rendered_list_items,
        id=list_id,
        cls="mb-4",
        uk_sortable="handle: .drag-handle",
        hx_trigger="moved",
        hx_post="/recipes/ui/update-diff",
        hx_target="#diff-content-wrapper",
        hx_swap="innerHTML",
        hx_include="closest form",
    )

    before_notstr, after_notstr = _build_diff_content_children(
        original_recipe, current_recipe.markdown
    )
    oob_diff_component = Div(
        before_notstr,
        after_notstr,
        hx_swap_oob="innerHTML:#diff-content-wrapper",
    )
    return list_component, oob_diff_component
