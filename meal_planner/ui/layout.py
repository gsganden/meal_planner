"""Layout components for the Meal Planner application, including sidebar and main
content area.
"""

from fasthtml.common import *
from monsterui.all import *


def sidebar():
    nav = NavContainer(
        Li(
            A(
                DivFullySpaced("Meal Planner"),
                href="/",
                hx_target="#content",
                hx_push_url="true",
            )
        ),
        NavParentLi(
            A(DivFullySpaced("Recipes")),
            NavContainer(
                Li(
                    A(
                        "Create",
                        href="/recipes/extract",
                        hx_target="#content",
                        hx_push_url="true",
                    )
                ),
                Li(
                    A(
                        "View All",
                        href="/recipes",
                        hx_target="#content",
                        hx_push_url="true",
                    )
                ),
                parent=False,
            ),
        ),
        uk_nav=True,
        cls=NavT.primary,
        uk_sticky="offset: 20",
    )
    return Div(nav, cls="space-y-4 p-4 w-full md:w-full")


def with_layout(title: str, *content):
    """Create a complete page with layout for full-page loads."""
    indicator_style = Style(
        """
        .htmx-indicator { opacity: 0; transition: opacity 200ms ease-in; }
        .htmx-indicator.htmx-request { opacity: 1; }
    """
    )

    hamburger_button = Div(
        Button(
            UkIcon("menu"),
            data_uk_toggle="target: #mobile-sidebar",
            cls="p-2",
        ),
        cls="md:hidden flex justify-end p-2",
    )

    mobile_sidebar_container = Div(
        sidebar(),
        id="mobile-sidebar",
        hidden=True,
    )

    return (
        Title(title),
        indicator_style,
        hamburger_button,
        mobile_sidebar_container,
        Div(cls="flex flex-col md:flex-row w-full")(
            Div(sidebar(), cls="hidden md:block w-1/5 max-w-52"),
            Div(
                H1(title, cls="text-3xl font-bold mb-6"),
                *content,
                cls="md:w-4/5 w-full p-4",
                id="content",
            ),
        ),
        Script(src="/static/recipe-editor.js"),
    )


def is_htmx(request: Request) -> bool:
    return "HX-Request" in request.headers
