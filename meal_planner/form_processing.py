"""Form data processing utilities for the Meal Planner application.

This module provides functions for processing and validating form data
from FastHTML forms, particularly for recipe creation and modification.
It handles the conversion of form data to Pydantic models with validation.
"""

from starlette.datastructures import FormData
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl

from meal_planner.models import RecipeBase


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


def process_recipe_form(form_data: dict) -> RecipeBase:
    """Convert form data to a validated RecipeBase model.
    
    Processes raw form data from recipe creation/edit forms, handling
    the special encoding of list fields (ingredients and instructions)
    and performing validation through Pydantic.
    
    Args:
        form_data: Dictionary of form field names to values. Expected keys:
            - "name": Recipe name (string)
            - "ingredients": Comma-separated ingredients (string)
            - "instructions": Newline-separated instructions (string)
    
    Returns:
        A validated RecipeBase instance with properly parsed lists.
        
    Raises:
        ValueError: If required fields are missing or validation fails.
    """
    return RecipeBase(
        name=form_data["name"],
        ingredients=[i.strip() for i in form_data["ingredients"].split(",")],
        instructions=form_data["instructions"].strip().split("\n"),
    )
