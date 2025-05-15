import html
import re

from meal_planner.models import RecipeBase


def postprocess_recipe(recipe: RecipeBase) -> RecipeBase:
    """Post-processes the extracted recipe data."""
    if recipe.name:
        recipe.name = _postprocess_recipe_name(recipe.name)

    recipe.ingredients = [
        processed_ing
        for ing_str in recipe.ingredients
        if (processed_ing := _postprocess_ingredient(ing_str))
    ]

    if not recipe.ingredients:
        raise ValueError(
            "Recipe must have at least one valid ingredient after processing."
        )

    recipe.instructions = [
        _postprocess_instruction(i)
        for i in recipe.instructions
        if (processed_inst := _postprocess_instruction(i))
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
