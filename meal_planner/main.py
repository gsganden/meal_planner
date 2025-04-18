import logging
import os
from typing import TypeVar

import fasthtml.common as fh
import google.generativeai as genai
import httpx
import instructor
import monsterui.all as mu
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


app = fh.FastHTMLWithLiveReload(hdrs=(mu.Theme.blue.headers()))
rt = app.route

MODEL_NAME = "gemini-2.0-flash"


@rt("/")
def get():
    main_content = mu.Titled("Home")
    return with_layout(main_content)


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
    name: str = Field(..., description="The name of the dish")


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
        logging.error("Error calling model {MODEL_NAME}: %s", e)
        return fh.Div(f"Error communicating with model {MODEL_NAME}")

    return fh.Div(extracted_recipe)


async def fetch_page_text(recipe_url: str):
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        response = await client.get(recipe_url)
    response.raise_for_status()
    return response.text


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag_name in ["script", "style", "nav", "header", "footer", "aside"]:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    main_content = soup.find("main")
    if main_content is not None:
        return main_content.get_text(separator=" ", strip=True)
    if soup.body is not None:
        return soup.body.get_text(separator=" ", strip=True)
    else:
        return html


T = TypeVar("T", bound=BaseModel)


async def call_llm(prompt: str, response_model: type[T]) -> T:
    client = instructor.from_gemini(
        client=genai.GenerativeModel(  # type: ignore
            model_name=f"models/{MODEL_NAME}",
        ),
        mode=instructor.Mode.GEMINI_JSON,
    )
    return client.chat.completions.create(  # type: ignore
        messages=[
            {"role": "user", "content": prompt},
        ],
        response_model=response_model,
    )


fh.serve()
