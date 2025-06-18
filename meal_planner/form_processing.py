"""Form data processing utilities for the Meal Planner application.

Converts form data to Pydantic models with validation.
"""

from typing import Optional

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

    Note:
        Empty strings and whitespace-only values are filtered out from
        ingredients and instructions lists.
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

    return {
        "name": name,
        "ingredients": ingredients,
        "instructions": instructions,
    }


def extract_recipe_id(form_data: FormData) -> Optional[int]:
    """Extract recipe ID from form data if present.

    Args:
        form_data: Starlette FormData object from the HTTP request.

    Returns:
        Recipe ID as integer if present and valid, None otherwise.
    """
    recipe_id_value = form_data.get("recipe_id")
    if recipe_id_value and isinstance(recipe_id_value, str):
        try:
            return int(recipe_id_value)
        except ValueError:
            return None
    return None


def generate_copy_name(original_name: str) -> str:
    """Generate a copy name by appending (Copy) or incrementing copy number.

    Args:
        original_name: The original recipe name.

    Returns:
        New name with appropriate copy suffix.

    Examples:
        "Pasta Recipe" -> "Pasta Recipe (Copy)"
        "Pasta Recipe (Copy)" -> "Pasta Recipe (Copy 2)"
        "Pasta Recipe (Copy 3)" -> "Pasta Recipe (Copy 4)"
    """
    import re

    # Check if it already has a numbered copy (e.g., "Recipe (Copy 3)")
    numbered_match = re.search(r"^(.+) \(Copy (\d+)\)$", original_name)
    if numbered_match:
        base_name = numbered_match.group(1)
        copy_number = int(numbered_match.group(2)) + 1
        return f"{base_name} (Copy {copy_number})"

    # Check if it ends with " (Copy)" exactly
    if original_name.endswith(" (Copy)"):
        return f"{original_name[:-7]} (Copy 2)"

    # Otherwise, add (Copy) at the end
    return f"{original_name} (Copy)"
