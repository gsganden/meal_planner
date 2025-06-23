"""UI components for recipe editing and display."""

import difflib
import html

import markdown
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
    """Generate HTML-safe diff components with proper markdown rendering.

    Convert full markdown to HTML first, then apply diff logic.
    This gives cleaner rendering without extra spacing.

    Args:
        before_text: Original markdown text for comparison.
        after_text: Modified markdown text to compare against original.

    Returns:
        Tuple of (before_items, after_items) where each is a list of
        FastHTML components representing the diff view with markdown rendering.
    """
    # Convert entire markdown to HTML first
    md = markdown.Markdown()
    before_html = md.convert(before_text)
    after_html = md.convert(after_text)

    # If content is the same, return as-is
    if before_text.strip() == after_text.strip():
        return [NotStr(before_html)], [NotStr(after_html)]

    # For different content, do line-by-line diff on original markdown
    before_lines = before_text.splitlines()
    after_lines = after_text.splitlines()

    # Filter out empty lines to reduce spacing
    before_lines = [line for line in before_lines if line.strip()]
    after_lines = [line for line in after_lines if line.strip()]

    matcher = difflib.SequenceMatcher(None, before_lines, after_lines)
    before_items = []
    after_items = []

    def process_line(line: str) -> str:
        """Convert markdown line to clean HTML."""
        line_html = md.convert(line).strip()
        if line_html.startswith("<p>") and line_html.endswith("</p>"):
            line_html = line_html[3:-4]
        return line_html

    def add_line(items_list: list, line: str, wrapper=None):
        """Add a processed line to the items list."""
        html = process_line(line)
        component = NotStr(html)
        if wrapper:
            component = wrapper(component)
        items_list.append(component)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in before_lines[i1:i2]:
                add_line(before_items, line)
                add_line(after_items, line)
        elif tag == "replace":
            for line in before_lines[i1:i2]:
                add_line(before_items, line, Del)
            for line in after_lines[j1:j2]:
                add_line(after_items, line, Ins)
        elif tag == "delete":
            for line in before_lines[i1:i2]:
                add_line(before_items, line, Del)
        elif tag == "insert":
            for line in after_lines[j1:j2]:
                add_line(after_items, line, Ins)

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
            Div(
                Style("""
                    .diff-content h1 {
                        font-size: 1.5rem;
                        font-weight: bold;
                        margin: 0;
                        line-height: 1.0;
                    }
                    .diff-content h2 {
                        font-size: 1.25rem;
                        font-weight: 600;
                        margin: 0;
                        line-height: 1.0;
                    }
                    .diff-content h3 {
                        font-size: 1.1rem;
                        font-weight: 600;
                        margin: 0 0 0.1rem 0;
                        line-height: 1.0;
                    }
                    .diff-content strong { font-weight: bold; }
                    .diff-content em { font-style: italic; }
                    .diff-content ul {
                        margin: 0;
                        padding-left: 1.5rem;
                        list-style-type: disc;
                    }
                    .diff-content li {
                        margin: 0;
                        display: list-item;
                        line-height: 1.3;
                    }
                    .diff-content p { margin: 0; line-height: 1.3; }
                    .diff-content ul p { margin: 0; }
                    .diff-content li p { margin: 0; display: inline; }
                """),
                *diff_items,
                id=pre_id,
                cls="border p-2 rounded bg-gray-100 dark:bg-gray-700 mt-1 "
                "overflow-auto text-sm diff-content",
                style="white-space: pre-wrap; overflow-wrap: break-word; "
                "font-family: monospace;",
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
    for ingredients and instructions in bulleted lists, and makes
    information if available.

    Args:
        recipe_data: Dictionary containing 'name', 'ingredients', 'instructions'
            and optionally 'makes_min', 'makes_max', 'makes_unit' fields from a recipe.

    Returns:
        MonsterUI Card component with formatted recipe display.
    """
    components = [H3(recipe_data["name"])]

    makes_min = recipe_data.get("makes_min")
    makes_max = recipe_data.get("makes_max")
    makes_unit = recipe_data.get("makes_unit", "servings")
    if makes_min is not None or makes_max is not None:
        if makes_min == makes_max:
            makes_text = f"Makes: {makes_min} {makes_unit}"
        elif makes_min is not None and makes_max is not None:
            makes_text = f"Makes: {makes_min}-{makes_max} {makes_unit}"
        elif makes_min is not None:
            makes_text = f"Makes: {makes_min}+ {makes_unit}"
        elif makes_max is not None:
            makes_text = f"Makes: up to {makes_max} {makes_unit}"

        components.append(P(Strong(html.escape(makes_text)), cls="mb-4"))

    components.extend(
        [
            H4("Ingredients"),
            Ul(
                *[Li(ing) for ing in recipe_data.get("ingredients", [])],
                cls=ListT.bullet,
            ),
        ]
    )

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

    if original_recipe.makes_min is not None:
        hidden_fields.append(
            Input(
                type="hidden",
                name="original_makes_min",
                value=str(original_recipe.makes_min),
            )
        )
    if original_recipe.makes_max is not None:
        hidden_fields.append(
            Input(
                type="hidden",
                name="original_makes_max",
                value=str(original_recipe.makes_max),
            )
        )
    if original_recipe.makes_unit is not None:
        hidden_fields.append(
            Input(
                type="hidden",
                name="original_makes_unit",
                value=original_recipe.makes_unit,
            )
        )

    return tuple(hidden_fields)


def _build_editable_section(current_recipe: RecipeBase):
    """Builds the 'Edit Manually' section."""
    name_input = _build_name_input(current_recipe.name)
    makes_section = build_makes_section(
        current_recipe.makes_min, current_recipe.makes_max, current_recipe.makes_unit
    )
    ingredients_section = _build_ingredients_section(current_recipe.ingredients)
    instructions_section = _build_instructions_section(current_recipe.instructions)

    return Div(
        H3("Edit Manually"),
        name_input,
        makes_section,
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


def build_makes_section(
    makes_min: int | None,
    makes_max: int | None,
    makes_unit: str | None,
    error_message: str | None = None,
):
    """Build the 'makes' section with min, max, and unit inputs.

    Handles creation of form fields for specifying recipe yield, including
    automatic adjustment logic via HTMX to ensure min <= max.

    Args:
        makes_min: Current minimum quantity.
        makes_max: Current maximum quantity.
        makes_unit: The unit of measurement (e.g., "servings", "cookies").
        error_message: Optional validation error message to display.

    Returns:
        A FastHTML component group containing the makes input fields.
    """
    makes_min_input = Div(
        FormLabel("Min", for_="makes_min"),
        Input(
            id="makes_min",
            name="makes_min",
            type="number",
            value=makes_min if makes_min is not None else "",
            min="1",
            hx_post="/recipes/ui/adjust-makes?changed=min",
            hx_target="#makes-section",
            hx_swap="outerHTML",
            hx_trigger="change",
            hx_include="closest form",
        ),
        cls="w-full",
    )

    makes_max_input = Div(
        FormLabel("Max", for_="makes_max"),
        Input(
            id="makes_max",
            name="makes_max",
            type="number",
            value=makes_max if makes_max is not None else "",
            min="1",
            hx_post="/recipes/ui/adjust-makes?changed=max",
            hx_target="#makes-section",
            hx_swap="outerHTML",
            hx_trigger="change",
            hx_include="closest form",
        ),
        cls="w-full",
    )

    makes_unit_input = Input(
        id="makes_unit",
        name="makes_unit",
        label="Unit",
        type="text",
        value=makes_unit or "",
        placeholder="servings, cookies, pieces",
        hx_post="/recipes/ui/update-diff",
        hx_target="#diff-content-wrapper",
        hx_swap="innerHTML",
        hx_trigger="change, keyup changed delay:500ms",
        hx_include="closest form",
    )

    components = [H4("Makes")]

    if error_message:
        components.append(P(error_message, cls="text-red-600 text-sm mb-2"))

    components.extend(
        [
            Div(
                Div(makes_min_input, style="width: 5rem;"),
                P("\u00a0to\u00a0"),
                Div(makes_max_input, style="width: 5rem;"),
                Div(makes_unit_input, style="flex: 1; margin-left: 0.75rem;"),
                cls="flex gap-3 items-end mb-2",
            ),
        ]
    )

    return Div(
        *components,
        cls="mb-4",
        id="makes-section",
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
