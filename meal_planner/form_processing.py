"""Form data processing utilities for the Meal Planner application.

Converts form data to Pydantic models with validation.
"""

from starlette.datastructures import FormData


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
            - "makes_min": Optional integer for minimum quantity
            - "makes_max": Optional integer for maximum quantity
            - "makes_unit": Optional string for quantity unit

    Note:
        Empty strings and whitespace-only values are filtered out from
        ingredients and instructions lists. Makes fields are converted
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

    # Parse makes fields
    makes_min = None
    makes_min_value = form_data.get(f"{prefix}makes_min")
    if isinstance(makes_min_value, str) and makes_min_value.strip():
        try:
            makes_min = int(makes_min_value.strip())
        except ValueError:
            makes_min = None

    makes_max = None
    makes_max_value = form_data.get(f"{prefix}makes_max")
    if isinstance(makes_max_value, str) and makes_max_value.strip():
        try:
            makes_max = int(makes_max_value.strip())
        except ValueError:
            makes_max = None

    makes_unit = None
    makes_unit_value = form_data.get(f"{prefix}makes_unit")
    if isinstance(makes_unit_value, str) and makes_unit_value.strip():
        makes_unit = makes_unit_value.strip()

    return {
        "name": name,
        "ingredients": ingredients,
        "instructions": instructions,
        "makes_min": makes_min,
        "makes_max": makes_max,
        "makes_unit": makes_unit,
    }
