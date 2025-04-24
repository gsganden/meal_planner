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
        ..., description='The name of the dish. Should not include the word "recipe"'
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


@rt("/recipes/extract/run")
async def post(recipe_url: str):
    try:
        page_text = clean_html(await fetch_page_text(recipe_url))
        logger.info("Successfully extracted recipe from: %s", recipe_url)
    except Exception as e:
        logger.error(
            "Error extracting recipe from %s: %s", recipe_url, e, exc_info=True
        )
        return fh.Div("Recipe extraction failed. Please check the URL and try again.")

    try:
        logging.info(f"Calling model {MODEL_NAME}")
        extracted_recipe: Recipe = await call_llm(
            prompt=f"Extract the recipe from the following HTML content: {page_text}",
            response_model=Recipe,
        )
        logging.info(f"Call to model {MODEL_NAME} successful")
    except Exception as e:
        logging.error(f"Error calling model {MODEL_NAME}: %s", e, exc_info=True)

    return fh.Div(extracted_recipe)


async def fetch_page_text(recipe_url: str):
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        response = await client.get(recipe_url)
    response.raise_for_status()
    return response.text


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    head = soup.find("head")

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

    body_content = soup.find("body")

    new_html = "<html>"
    if head:
        new_html += str(head)
    if body_content:
        new_html += str(body_content)
    else:
        temp_soup_str = str(soup)
        if temp_soup_str.startswith("<html>"):
            temp_soup_str = temp_soup_str[len("<html>") :]
        if temp_soup_str.endswith("</html>"):
            temp_soup_str = temp_soup_str[: -len("</html>")]
        new_html += temp_soup_str

    new_html += "</html>"

    return new_html


class ContainsRecipe(BaseModel):
    contains_recipe: bool = Field(
        ..., description="Whether the provided text contains a recipe (True or False)"
    )


async def page_contains_recipe(page_text: str) -> bool:
    """
    Uses an LLM to determine if the given text contains a recipe.
    """
    prompt = f"""Analyze the following text and determine if it represents a food recipe.
        Look for elements like ingredients lists, cooking instructions, serving sizes, etc.
        Respond with only True or False.

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


fh.serve()
