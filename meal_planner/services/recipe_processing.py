import html
import re

from meal_planner.models import RecipeBase


def postprocess_recipe(recipe: RecipeBase) -> RecipeBase:
    """Post-processes the extracted recipe data."""
    if recipe.name:
        recipe.name = _postprocess_recipe_name(recipe.name)

    processed_ingredients = []
    # Process ingredients only if the list exists and is not empty initially
    # Note: recipe.ingredients could be None if not provided by Pydantic model,
    # though default_factory=list should prevent None.
    # If it's an empty list, this block is skipped.
    if recipe.ingredients:
        for i in recipe.ingredients:
            processed_ing = _postprocess_ingredient(i)
            if processed_ing:  # Only add if not empty after processing
                processed_ingredients.append(processed_ing)

    # If, after processing, the list is empty (it might have been initially empty,
    # or contained only strippable items like [" "])
    # then populate with placeholder to satisfy min_length=1.
    if not processed_ingredients:
        recipe.ingredients = ["No ingredients found"]
    else:
        recipe.ingredients = processed_ingredients

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
    instruction = instruction.strip()
    return re.sub(
        r"^\s*(?:Step\s*\d+|\d+)\s*[:.]?\s*", "", instruction, flags=re.IGNORECASE
    )


def _close_parenthesis(text: str) -> str:
    """Appends a closing parenthesis if an opening one exists without a closing one."""
    if "(" in text and ")" not in text:
        return text + ")"
    return text
