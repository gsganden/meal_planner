import logging
import os
from typing import TypeVar

import fasthtml.common as fh
import httpx
import instructor
import monsterui.all as mu
from bs4 import BeautifulSoup
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def _check_api_key():
    if "GOOGLE_API_KEY" not in os.environ:
        logger.error("GOOGLE_API_KEY environment variable not set.")
        raise SystemExit("GOOGLE_API_KEY environment variable not set.")


_check_api_key()

openai_client = AsyncOpenAI(
    api_key=os.environ["GOOGLE_API_KEY"],
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

aclient = instructor.from_openai(openai_client)

app = fh.FastHTMLWithLiveReload(hdrs=(mu.Theme.blue.headers()))
rt = app.route

MODEL_NAME = "gemini-2.0-flash"


@rt("/")
def get():
    return with_layout(mu.Titled("Home"))


def sidebar():
    nav = mu.NavContainer(
        fh.Li(
            fh.A(
                mu.DivFullySpaced("Home"),
                href="/",
                hx_target="#content",
                hx_push_url="true",
            )
        ),
        mu.NavParentLi(
            fh.A(mu.DivFullySpaced("Recipes")),
            mu.NavContainer(
                fh.Li(
                    fh.A(
                        "Extract",
                        href="/recipes/extract",
                        hx_target="#content",
                        hx_push_url="true",
                    )
                ),
                parent=False,
            ),
        ),
        uk_nav=True,
        cls=mu.NavT.primary,
    )
    return fh.Div(nav, cls="space-y-4 p-4 w-full md:w-full")


def with_layout(content):
    indicator_style = fh.Style("""
        .htmx-indicator { opacity: 0; transition: opacity 200ms ease-in; }
        .htmx-indicator.htmx-request { opacity: 1; }
    """)
    return (
        fh.Title("Meal Planner"),
        indicator_style,
        fh.Div(cls="flex flex-col md:flex-row w-full")(
            fh.Div(sidebar(), cls="hidden md:block w-1/5 max-w-52"),
            fh.Div(content, cls="md:w-4/5 w-full p-4", id="content"),
        ),
    )


class Recipe(BaseModel):
    name: str = Field(
        ...,
        description="""
            The exact name of the dish as found in the text, including all punctuation.
            Should NOT include the word "recipe".
            """,
    )


@rt("/recipes/extract")
def get():
    initial_form = mu.Form(
        mu.Input(
            id="recipe_url",
            name="recipe_url",
            type="url",
            placeholder="Enter Recipe URL",
        ),
        fh.Div(
            mu.Button("Extract Recipe"),
            mu.Loading(
                id="extract-indicator",
                cls="htmx-indicator ml-2",
            ),
        ),
        hx_post="/recipes/extract/run",
        hx_target="#recipe-results",
        hx_swap="innerHTML",
        hx_indicator="#extract-indicator",
        id="extract-form",
    )
    results_div = fh.Div(id="recipe-results")
    return with_layout(
        mu.Titled("Extract Recipe", fh.Div(initial_form, results_div), id="content")
    )


async def fetch_page_text(recipe_url: str):
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        response = await client.get(recipe_url)
    response.raise_for_status()
    return response.text


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    tags_to_remove = ["script", "style", "nav", "footer", "aside"]
    for tag_name in tags_to_remove:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    for ad_selector in [".ad", "#ads", "[class*=advert]", "[id*=banner]"]:
        try:
            for tag in soup.select(ad_selector):
                tag.decompose()
        except Exception as e:
            logger.warning(f"CSS selector failed: {ad_selector} - {e}")

    return str(soup)


class ContainsRecipe(BaseModel):
    contains_recipe: bool = Field(
        ..., description="Whether the provided text contains a recipe (True or False)"
    )


async def page_contains_recipe(page_text: str) -> bool:
    """
    Uses an LLM to determine if the given text contains a recipe.
    """
    prompt = f"""Analyze the following text and determine if it represents a food
        recipe. Look for elements like ingredients lists, cooking instructions, serving
        sizes, etc. Respond with only True or False.

        Text:
        ---
        {page_text[:999999]} # Limit text size to avoid excessive token usage
        ---
        Does the text contain a recipe?
        """
    try:
        response = await call_llm(prompt=prompt, response_model=ContainsRecipe)
        logger.info(f"LLM determined contains_recipe: {response.contains_recipe}")
        return response.contains_recipe
    except Exception as e:
        logger.error(f"Error calling LLM in page_contains_recipe: {e}", exc_info=True)
        return False


T = TypeVar("T", bound=BaseModel)


async def call_llm(prompt: str, response_model: type[T]) -> T:
    response = await aclient.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "user", "content": prompt},
        ],
        response_model=response_model,
    )
    return response


async def extract_recipe_from_url(recipe_url: str) -> Recipe:
    """Fetches, cleans, extracts, and post-processes a recipe from a URL."""
    try:
        raw_text = await fetch_page_text(recipe_url)
        page_text = clean_html(raw_text)
        logger.info("Successfully fetched and cleaned text from: %s", recipe_url)
    except Exception as e:
        logger.error(
            "Error fetching or cleaning page text from %s: %s",
            recipe_url,
            e,
            exc_info=True,
        )
        raise

    try:
        logging.info(f"Calling model {MODEL_NAME} for URL: {recipe_url}")
        prompt = f"""Please extract the recipe from the following HTML content. The
        recipe name MUST be extracted exactly as it appears.

        HTML Content:
        {page_text}
        """
        extracted_recipe: Recipe = await call_llm(
            prompt=prompt,
            response_model=Recipe,
        )
        logging.info(f"Call to model {MODEL_NAME} successful for URL: {recipe_url}")

        processed_recipe = postprocess_recipe(extracted_recipe)
        return processed_recipe

    except Exception as e:
        logger.error(
            f"Error calling model {MODEL_NAME} or postprocessing for URL {recipe_url}: "
            "%s",
            e,
            exc_info=True,
        )
        raise


def postprocess_recipe(recipe: Recipe) -> Recipe:
    """Post-processes the extracted recipe data."""
    if recipe.name:
        name_lower = recipe.name.lower()
        if "recipe" in name_lower:
            recipe_index = name_lower.find("recipe")
            original_case_recipe = recipe.name[
                recipe_index : recipe_index + len("recipe")
            ]
            recipe.name = recipe.name.replace(original_case_recipe, "").strip()
            logger.info(
                f"Removed 'recipe' from name. Before title casing: {recipe.name}"
            )

        recipe.name = recipe.name.title()
        logger.info(f"Applied title case. Final name: {recipe.name}")

    return recipe


@rt("/recipes/extract/run")
async def post(recipe_url: str):
    try:
        # Call the helper function
        processed_recipe = await extract_recipe_from_url(recipe_url)
        # Render the successful result
        return fh.Div(processed_recipe)
    except httpx.RequestError as e:
        logger.error(
            "HTTP Request Error extracting recipe from %s: %s",
            recipe_url,
            e,
            exc_info=True,
        )
        return fh.Div(f"Error fetching URL: {e}. Please check the URL and try again.")
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP Status Error extracting recipe from %s: %s",
            recipe_url,
            e,
            exc_info=True,
        )
        return fh.Div(
            f"Error fetching URL: Received status {e.response.status_code}. Please "
            "check the URL."
        )
    except Exception as e:
        logger.error(
            "Generic error processing recipe from %s: %s", recipe_url, e, exc_info=True
        )
        return fh.Div("Recipe extraction failed. An unexpected error occurred.")


fh.serve()
