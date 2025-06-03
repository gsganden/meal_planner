"""Layout components and utilities for the Meal Planner application.

This module provides the main page layout structure including sidebar navigation,
header, and content wrappers. It also includes utilities for detecting HTMX
requests to support partial page updates.
"""

from fasthtml.common import *
from monsterui.all import *


def sidebar():
    """Generate the application sidebar with navigation links.

    Creates a responsive sidebar component with navigation menu items
    for all main application sections. Uses MonsterUI components with
    proper styling and hover effects.

    Returns:
        Sidebar component containing navigation links and branding.
    """
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
    """Wrap content in the standard application layout.

    Provides consistent page structure with sidebar navigation, header,
    and content area. Sets the page title and wraps all content in the
    application's standard layout components.

    Args:
        title: Page title to display in browser tab and header.
        *content: Variable number of FastHTML components to render
            in the main content area.

    Returns:
        Complete HTML page with layout wrapper and provided content.
    """
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

    github_link = Div(
        UkIconLink(
            "github",
            href="https://github.com/gsganden/meal_planner",
            target="_blank",
            cls="text-gray-500 hover:text-gray-700",
            rel="noopener",
            title="View source code on GitHub",
            **{"aria-label": "View source code on GitHub"},
        ),
        cls="fixed bottom-4 right-4",
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
        github_link,
        Script(src="/static/recipe-editor.js"),
    )


def is_htmx(request: Request) -> bool:
    """Check if the current request is from HTMX.

    Examines request headers to determine if the request was initiated
    by HTMX, which is used to decide whether to return a full page
    or just a content fragment.

    Args:
        request: FastAPI/Starlette request object.

    Returns:
        True if the request includes the HX-Request header, False otherwise.
    """
    return request.headers.get("HX-Request") == "true"
