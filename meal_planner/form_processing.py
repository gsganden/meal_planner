"""Form data processing utilities for the Meal Planner application.

Converts form data to Pydantic models with validation.
"""

from starlette.datastructures import FormData


def normalize_servings_values(
    servings_min: int | None, servings_max: int | None
) -> tuple[int | None, int | None]:
    """Normalize servings values based on user requirements.

    If only one serving value is provided, sets both min and max to that value.
    This handles the case where users enter a single serving count.

    Args:
        servings_min: Optional minimum servings value
        servings_max: Optional maximum servings value

    Returns:
        Tuple of (normalized_min, normalized_max) where if only one value
        was provided, both will be set to that value.
    """
    # If only min is provided, set max to the same value
    if servings_min is not None and servings_max is None:
        return servings_min, servings_min

    # If only max is provided, set min to the same value
    if servings_max is not None and servings_min is None:
        return servings_max, servings_max

    # If both are provided or both are None, return as-is
    return servings_min, servings_max


def parse_recipe_form_data(form_data: FormData, prefix: str = "") -> dict:
    """Parse recipe form data from multipart form submission.

    Extracts and cleans recipe data from FormData, handling multi-value
    fields for ingredients and instructions. Supports prefixed field names
    for forms with multiple recipe sections.

    Args:
        form_data: Starlette FormData object from the HTTP request.
        prefix: Optional prefix for form field names, used when multiple
            recipe forms exist on the same page. If "edit_", looks for
            fields like "edit_name", "edit_ingredients", etc.

    Returns:
        Dictionary with cleaned recipe data containing:
            - "name": Recipe name as string
            - "ingredients": List of non-empty ingredient strings
            - "instructions": List of non-empty instruction strings
            - "servings_min": Optional integer for minimum servings
            - "servings_max": Optional integer for maximum servings

    Note:
        Empty strings and whitespace-only values are filtered out from
        ingredients and instructions lists. Servings fields are converted
        to integers if valid, otherwise set to None.
    """
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

    # Parse servings fields
    servings_min = None
    servings_min_value = form_data.get(f"{prefix}servings_min")
    if isinstance(servings_min_value, str) and servings_min_value.strip():
        try:
            servings_min = int(servings_min_value.strip())
        except ValueError:
            servings_min = None

    servings_max = None
    servings_max_value = form_data.get(f"{prefix}servings_max")
    if isinstance(servings_max_value, str) and servings_max_value.strip():
        try:
            servings_max = int(servings_max_value.strip())
        except ValueError:
            servings_max = None

    # Normalize servings values (if only one is provided, set both to that value)
    servings_min, servings_max = normalize_servings_values(servings_min, servings_max)

    return {
        "name": name,
        "ingredients": ingredients,
        "instructions": instructions,
        "servings_min": servings_min,
        "servings_max": servings_max,
    }
