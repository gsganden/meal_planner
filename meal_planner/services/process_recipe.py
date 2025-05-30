"""Functions for post-processing and cleaning recipe data."""

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
        processed_inst
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
    return _ensure_ending_punctuation(
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


def _ensure_ending_punctuation(text: str) -> str:
    """Adds a period at the end of text if it doesn't end with punctuation.

    For text ending with a closing parenthesis, ensures there's a period
    before the closing parenthesis if needed.
    """
    if not text:
        return text

    ending_punctuation = [".", "!", "?", ":", ";"]

    if text[-1] in ending_punctuation:
        return text

    if text.endswith(")"):
        if len(text) > 1 and text[-2] not in ending_punctuation:
            return text[:-1] + "." + text[-1]
        return text

    return text + "."
