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
            - "source": Optional source URL/reference as string or None
            - "ingredients": List of non-empty ingredient strings
            - "instructions": List of non-empty instruction strings

    Note:
        Empty strings and whitespace-only values are filtered out from
        ingredients and instructions lists. Source field allows empty values.
    """
    name_value = form_data.get(f"{prefix}name")
    name = name_value if isinstance(name_value, str) else ""

    source_value = form_data.get(f"{prefix}source")
    source = (
        source_value.strip()
        if isinstance(source_value, str) and source_value.strip()
        else None
    )

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
        "source": source,
        "ingredients": ingredients,
        "instructions": instructions,
    }
