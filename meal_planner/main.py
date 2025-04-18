import logging

import fasthtml.common as fh
import httpx
import monsterui.all as mu

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


app = fh.FastHTMLWithLiveReload(hdrs=(mu.Theme.blue.headers()))
rt = app.route


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
    return fh.Title("Meal Planner"), fh.Div(cls="flex flex-col md:flex-row w-full")(
        fh.Div(sidebar(), cls="hidden md:block w-1/5 max-w-52"),
        fh.Div(content, cls="md:w-4/5 w-full p-4", id="content"),
    )


@rt("/recipes/extract")
def recipes_extract():
    initial_form = mu.Form(
        mu.Input(
            id="recipe_url",
            name="recipe_url",
            type="url",
            placeholder="Enter Recipe URL",
        ),
        mu.Button("Extract Recipe"),
        hx_post="/recipes/extract/run",
        hx_target="#recipe-results",
        hx_swap="innerHTML",
        id="extract-form",
    )
    results_div = fh.Div(id="recipe-results")
    return with_layout(
        mu.Titled("Extract Recipe", fh.Div(initial_form, results_div), id="content")
    )


@rt("/recipes/extract/run")
async def post(recipe_url: str):
    try:
        page_text = await fetch_page_text(recipe_url)
        logger.info("Successfully extracted recipe from: %s", recipe_url)
        return fh.Div(page_text)
    except Exception as e:
        logger.error(
            "Error extracting recipe from %s: %s", recipe_url, e, exc_info=True
        )
        return fh.Div("Recipe extraction failed. Please check the URL and try again.")


async def fetch_page_text(recipe_url: str):
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        response = await client.get(recipe_url)
    response.raise_for_status()
    return response.text


fh.serve()
