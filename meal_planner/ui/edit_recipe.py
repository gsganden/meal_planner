"""UI components for recipe editing and display."""

import difflib
import html

from bs4.element import Tag
from fasthtml.common import *
from monsterui.all import *

from meal_planner.models import RecipeBase
from meal_planner.ui.common import (
    DRAG_HANDLE_ICON,
    ICON_ADD,
    ICON_DELETE,
    create_loading_indicator,
)


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
                # Escape HTML entities to prevent XSS attacks
                escaped_line = html.escape(line)
                before_items.extend([escaped_line, "\n"])
                after_items.extend([escaped_line, "\n"])
        elif tag == "replace":
            for line in before_lines[i1:i2]:
                before_items.extend([Del(html.escape(line)), "\n"])
            for line in after_lines[j1:j2]:
                after_items.extend([Ins(html.escape(line)), "\n"])
        elif tag == "delete":
            for line in before_lines[i1:i2]:
                before_items.extend([Del(html.escape(line)), "\n"])
        elif tag == "insert":
            for line in after_lines[j1:j2]:
                after_items.extend([Ins(html.escape(line)), "\n"])

    if before_items and before_items[-1] == "\n":
        before_items.pop()
    if after_items and after_items[-1] == "\n":
        after_items.pop()

    return before_items, after_items


def build_diff_content_children(
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


def build_recipe_display(recipe_data: dict) -> FT:
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


def build_edit_review_form(
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
        create_loading_indicator("modify-indicator"),
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


def render_ingredient_list_items(ingredients: list[str]) -> list[Tag]:
    """Render ingredient input divs as a list of fasthtml.Tag components."""
    items_list = []
    for i, ing_value in enumerate(ingredients):
        drag_handle_component = DRAG_HANDLE_ICON
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
            ICON_DELETE,
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
    ingredient_item_components = render_ingredient_list_items(ingredients)

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
        ICON_ADD,
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


def render_instruction_list_items(instructions: list[str]) -> list[Tag]:
    """Render instruction textarea divs as a list of fasthtml.Tag components."""
    items_list = []
    for i, inst_value in enumerate(instructions):
        drag_handle_component = DRAG_HANDLE_ICON
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
            ICON_DELETE,
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
    instruction_item_components = render_instruction_list_items(instructions)

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
        ICON_ADD,
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
    before_component, after_component = build_diff_content_children(
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
        ),
        id="review-card",
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
        create_loading_indicator("save-indicator"),
        id="save-button-container",
        cls="mt-6",
    )


def build_modify_form_response(
    current_recipe: RecipeBase,
    original_recipe: RecipeBase,
    modification_prompt_value: str,
    error_message_content: FT | None,
) -> Div:
    """Builds the common HTML response for the recipe modification form."""
    edit_form_card, review_section_card = build_edit_review_form(
        current_recipe=current_recipe,
        original_recipe=original_recipe,
        modification_prompt_value=modification_prompt_value,
        error_message_content=error_message_content,
    )
    return Div(
        edit_form_card,
        Div(
            review_section_card,
            hx_swap_oob="innerHTML:#review-section-target",
        ),
        id="edit-form-target",
        cls="mt-6",
    )
