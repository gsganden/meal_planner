"""UI components for recipe editing and display."""

import difflib
import html

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
    """Generate HTML-safe diff components for before/after text comparison.

    Create a line-by-line comparison, with proper HTML escaping to prevent XSS attacks.
    Differences are marked with Del/Ins FastHTML components for styling.

    Args:
        before_text: Original text for comparison.
        after_text: Modified text to compare against original.

    Returns:
        Tuple of (before_items, after_items) where each is a list of
        FastHTML components and strings representing the diff view.
    """
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
    """Build styled diff view cards showing recipe changes.

    Creates two card components showing the before/after state of a recipe
    with visual highlighting of additions, deletions, and modifications.

    Args:
        original_recipe: The baseline recipe to compare against.
        current_markdown: Markdown representation of the current recipe state.

    Returns:
        Tuple of (before_card, after_card) MonsterUI Card components
        styled for diff display.
    """

    def _build_single_diff_pane(
        title: str,
        diff_items: list[str | FT],
        pre_id: str,
    ) -> Card:
        """Build a single pane (before or after) for the recipe diff view."""
        return Card(
            Strong(title),
            Pre(
                *diff_items,
                id=pre_id,
                cls="border p-2 rounded bg-gray-100 dark:bg-gray-700 mt-1 overflow-auto"
                "text-xs",
                style="white-space: pre-wrap; overflow-wrap: break-word;",
            ),
            cls=CardT.secondary,
        )

    before_items, after_items = generate_diff_html(
        original_recipe.markdown, current_markdown
    )

    return (
        _build_single_diff_pane(
            title="Initial Extracted Recipe (Reference)",
            diff_items=before_items,
            pre_id="diff-before-pre",
        ),
        _build_single_diff_pane(
            title="Current Edited Recipe",
            diff_items=after_items,
            pre_id="diff-after-pre",
        ),
    )


def build_recipe_display(recipe_data: dict) -> FT:
    """Build a formatted display card for a recipe.

    Creates a read-only view of recipe data with proper formatting
    for ingredients and instructions in bulleted lists, and servings
    information if available.

    Args:
        recipe_data: Dictionary containing 'name', 'ingredients', 'instructions'
            and optionally 'servings_min', 'servings_max' fields from a recipe.

    Returns:
        MonsterUI Card component with formatted recipe display.
    """
    components = [H3(recipe_data["name"])]

    # Add servings information if available
    servings_min = recipe_data.get("servings_min")
    servings_max = recipe_data.get("servings_max")
    if servings_min is not None or servings_max is not None:
        if servings_min == servings_max:
            servings_text = f"Serves: {servings_min}"
        elif servings_min is not None and servings_max is not None:
            servings_text = f"Serves: {servings_min}-{servings_max}"
        elif servings_min is not None:
            servings_text = f"Serves: {servings_min}+"
        elif servings_max is not None:
            servings_text = f"Serves: up to {servings_max}"

        components.append(P(Strong(servings_text), cls="mb-4"))

    components.extend([
        H4("Ingredients"),
        Ul(
            *[Li(ing) for ing in recipe_data.get("ingredients", [])],
            cls=ListT.bullet,
        ),
    ])

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
    """Build the complete recipe editing interface with review section.

    Constructs the main editing interface including AI modification controls,
    manual edit fields, diff view, and save functionality. This is the primary
    UI component for the recipe editing workflow.

    Args:
        current_recipe: The RecipeBase object representing the current state
            of the recipe being edited.
        original_recipe: Optional RecipeBase object representing the initial
            state before any edits. Used as baseline for diff view. If None,
            current_recipe is used as baseline.
        modification_prompt_value: Optional string containing the user's
            previous AI modification request, used to pre-fill the input.
        error_message_content: Optional FastHTML content (e.g., Div with error
            message) to display within the modification controls section.

    Returns:
        Tuple containing:
        1. main_edit_card: Card with modification controls and editable fields
        2. review_section_card: Card with diff view and save button
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
    hidden_fields = [
        Input(type="hidden", name="original_name", value=original_recipe.name),
        *(
            Input(type="hidden", name="original_ingredients", value=ing)
            for ing in original_recipe.ingredients
        ),
        *(
            Input(type="hidden", name="original_instructions", value=inst)
            for inst in original_recipe.instructions
        ),
    ]

    # Add servings fields if they have values
    if original_recipe.servings_min is not None:
        hidden_fields.append(
            Input(
                type="hidden",
                name="original_servings_min",
                value=str(original_recipe.servings_min),
            )
        )
    if original_recipe.servings_max is not None:
        hidden_fields.append(
            Input(
                type="hidden",
                name="original_servings_max",
                value=str(original_recipe.servings_max),
            )
        )

    return tuple(hidden_fields)


def _build_editable_section(current_recipe: RecipeBase):
    """Builds the 'Edit Manually' section with inputs for name, servings, ingredients.

    and instructions.
    """
    name_input = _build_name_input(current_recipe.name)
    servings_section = _build_servings_section(
        current_recipe.servings_min, current_recipe.servings_max
    )
    ingredients_section = _build_ingredients_section(current_recipe.ingredients)
    instructions_section = _build_instructions_section(current_recipe.instructions)

    return Div(
        H3("Edit Manually"),
        name_input,
        servings_section,
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


def _build_servings_section(servings_min: int | None, servings_max: int | None):
    """Builds the servings input section with separate min/max fields."""
    servings_min_input = Input(
        id="servings_min",
        name="servings_min",
        label="Minimum Servings",
        type="number",
        value=str(servings_min) if servings_min is not None else "",
        placeholder="e.g., 4",
        min="1",
        cls="mr-2",
        hx_post="/recipes/ui/update-diff",
        hx_target="#diff-content-wrapper",
        hx_swap="innerHTML",
        hx_trigger="change, keyup changed delay:500ms",
        hx_include="closest form",
    )

    servings_max_input = Input(
        id="servings_max",
        name="servings_max",
        label="Maximum Servings",
        type="number",
        value=str(servings_max) if servings_max is not None else "",
        placeholder="e.g., 6",
        min="1",
        cls="ml-2",
        hx_post="/recipes/ui/update-diff",
        hx_target="#diff-content-wrapper",
        hx_swap="innerHTML",
        hx_trigger="change, keyup changed delay:500ms",
        hx_include="closest form",
    )

    return Div(
        H4("Servings"),
        Div(
            servings_min_input,
            servings_max_input,
            cls="flex gap-4",
        ),
        cls="mb-4",
    )


def render_ingredient_list_items(ingredients: list[str]) -> list[FT]:
    """Render draggable ingredient input fields as FastHTML components.

    Creates a list of ingredient input fields with drag handles for reordering
    and delete buttons. Each input triggers diff updates on change.

    Args:
        ingredients: List of ingredient strings to render.

    Returns:
        List of Div components, each containing an ingredient input with controls.
    """
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


def render_instruction_list_items(instructions: list[str]) -> list[FT]:
    """Render draggable instruction textarea fields as FastHTML components.

    Creates a list of instruction textareas with drag handles for reordering
    and delete buttons. Each textarea triggers diff updates on change.

    Args:
        instructions: List of instruction strings to render.

    Returns:
        List of Div components, each containing an instruction textarea with controls.
    """
    items_list = []
    for i, inst_value in enumerate(instructions):
        drag_handle_component = DRAG_HANDLE_ICON
        textarea_component = TextArea(
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
    """Build the complete form response for recipe modification requests.

    Wraps the edit form and review section with proper HTMX attributes
    for out-of-band swaps. Used as the standard response format for
    modification endpoints.

    Args:
        current_recipe: Current state of the recipe after modifications.
        original_recipe: Original recipe state for diff comparison.
        modification_prompt_value: AI modification prompt to display.
        error_message_content: Optional error message to show.

    Returns:
        Div containing the edit form and OOB review section update.
    """
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
