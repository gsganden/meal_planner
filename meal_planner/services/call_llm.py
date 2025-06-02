"""Provides functions to interact with a Large Language Model (LLM).

for recipe extraction and modification, using structured Pydantic models.
"""

import asyncio
import logging
import os
import string
from pathlib import Path
from typing import TypeVar

import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel

from meal_planner.models import RecipeBase

MODEL_NAME = "gemini-2.0-flash"
PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompt_templates"
ACTIVE_RECIPE_EXTRACTION_PROMPT_FILE = (
    "20250530_162003__prioritize_explicit_ingredients.txt"
)
ACTIVE_RECIPE_MODIFICATION_PROMPT_FILE = "20250525_174436__string_template_syntax.txt"

logger = logging.getLogger(__name__)

_openai_client = None
_aclient = None

T = TypeVar("T", bound=BaseModel)


_client_lock = asyncio.Lock()


async def _get_aclient():
    """Lazy initialization of the instructor client."""
    global _openai_client, _aclient
    if _aclient is None:
        async with _client_lock:
            if _aclient is None:  # Double-check pattern
                _openai_client = AsyncOpenAI(
                    api_key=os.environ["GOOGLE_API_KEY"],
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                )
                _aclient = instructor.from_openai(_openai_client)
    return _aclient


async def get_structured_llm_response(prompt: str, response_model: type[T]) -> T:
    """Queries the LLM with a prompt and returns a Pydantic model instance.

    Args:
        prompt: The prompt to send to the LLM.
        response_model: The Pydantic model to structure the LLM's response.

    Returns:
        An instance of the provided Pydantic model.

    Raises:
        Exception: If the LLM call fails or the response cannot be parsed.
    """
    try:
        logger.info(
            "LLM Call: model=%s, response_model=%s", MODEL_NAME, response_model.__name__
        )
        aclient = await _get_aclient()
        response = await aclient.chat.completions.create(
            model=MODEL_NAME,
            response_model=response_model,
            messages=[{"role": "user", "content": prompt}],
        )
        logger.debug("LLM Response: %s", response)
        return response
    except Exception as e:
        logger.error(
            "LLM Call Error: model=%s, response_model=%s, error=%s",
            MODEL_NAME,
            response_model.__name__,
            e,
            exc_info=True,
        )
        raise


def _get_llm_prompt_path(category: str, filename: str) -> Path:
    """Constructs the full path to a prompt file for LLM services."""
    return PROMPT_DIR / category / filename


async def generate_recipe_from_text(text: str) -> RecipeBase:
    """Extracts a structured recipe from a given block of text using an LLM.

    This function takes unstructured text, presumably containing a recipe,
    formats it into a prompt using a predefined template, and then queries
    an LLM to parse this text into a structured `RecipeBase` object.

    Args:
        text: A string containing the raw text of the recipe to be extracted.

    Returns:
        A `RecipeBase` Pydantic model instance populated with the extracted
        recipe data (name, ingredients, instructions).

    Raises:
        FileNotFoundError: If the configured prompt template file for recipe
            extraction cannot be found at the expected path.
        RuntimeError: If any other error occurs during the LLM call or
            response processing, wrapping the original exception. This typically
            indicates an issue with the LLM service itself or an unexpected
            problem formatting the prompt or parsing the response.
    """
    logger.info("Starting recipe generation from text.")
    try:
        prompt_file_path = _get_llm_prompt_path(
            "recipe_extraction", ACTIVE_RECIPE_EXTRACTION_PROMPT_FILE
        )
        logger.info("Using extraction prompt file: %s", prompt_file_path.name)
        prompt_template = prompt_file_path.read_text(encoding="utf-8")
        formatted_prompt = string.Template(prompt_template).safe_substitute(
            page_text=text
        )

        extracted_recipe: RecipeBase = await get_structured_llm_response(
            prompt=formatted_prompt,
            response_model=RecipeBase,
        )
        logger.info("LLM successfully generated recipe: %s", extracted_recipe.name)
        return extracted_recipe
    except FileNotFoundError as e:
        logger.error("Prompt file not found: %s", e, exc_info=True)
        raise
    except Exception as e:
        logger.error(
            "Error during LLM recipe generation from text: %s", e, exc_info=True
        )
        raise RuntimeError(
            "LLM service error during recipe generation from text."
        ) from e


async def generate_modified_recipe(
    current_recipe: RecipeBase, modification_request: str
) -> RecipeBase:
    """Modifies an existing recipe based on a textual request using an LLM.

    This function takes a current `RecipeBase` object and a natural language
    modification request. It formats these into a prompt using a predefined
    template, then queries an LLM to generate a new `RecipeBase` object
    reflecting the requested modifications.

    Args:
        current_recipe: The `RecipeBase` Pydantic model instance representing
            the recipe to be modified. Its markdown representation is used in
            the prompt.
        modification_request: A string containing the user's instructions
            on how to modify the `current_recipe`.

    Returns:
        A new `RecipeBase` Pydantic model instance representing the recipe
        after the LLM has applied the requested modifications.

    Raises:
        FileNotFoundError: If the configured prompt template file for recipe
            modification cannot be found at the expected path.
        RuntimeError: If any other error occurs during the LLM call or
            response processing, wrapping the original exception. This typically
            indicates an issue with the LLM service itself or an unexpected
            problem formatting the prompt or parsing the response.
    """
    logger.info(
        "Starting recipe modification. Original: %s, Request: %s",
        current_recipe.name,
        modification_request,
    )
    try:
        prompt_file_path = _get_llm_prompt_path(
            "recipe_modification", ACTIVE_RECIPE_MODIFICATION_PROMPT_FILE
        )
        logger.info("Using modification prompt file: %s", prompt_file_path.name)
        modification_template = prompt_file_path.read_text()
        formatted_prompt = string.Template(modification_template).safe_substitute(
            current_recipe_markdown=current_recipe.markdown,
            modification_prompt=modification_request,
        )

        modified_recipe: RecipeBase = await get_structured_llm_response(
            prompt=formatted_prompt,
            response_model=RecipeBase,
        )
        logger.info(
            "LLM successfully generated modified recipe: %s", modified_recipe.name
        )
        return modified_recipe
    except FileNotFoundError as e:
        logger.error("Prompt file not found: %s", e, exc_info=True)
        raise
    except Exception as e:
        logger.error("Error during LLM recipe modification: %s", e, exc_info=True)
        raise RuntimeError("LLM service error during recipe modification.") from e
