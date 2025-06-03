"""Common UI components and constants used across the Meal Planner application."""

from monsterui.all import *

CSS_ERROR_CLASS = str(TextT.error)
CSS_SUCCESS_CLASS = str(TextT.success)

ICON_DELETE = UkIcon("minus-circle", cls=CSS_ERROR_CLASS)
ICON_ADD = UkIcon("plus-circle", cls=str(TextT.primary))
DRAG_HANDLE_ICON = UkIcon(
    "menu", cls="drag-handle mr-2 cursor-grab text-gray-400 hover:text-gray-600"
)


def create_loading_indicator(indicator_id: str) -> Loading:
    """Create a standard loading spinner for HTMX requests.

    Generates a MonsterUI Loading component configured as an HTMX indicator
    that shows/hides automatically during async operations.

    Args:
        indicator_id: HTML ID for the loading indicator element.

    Returns:
        Loading component with HTMX indicator class and styling.
    """
    return Loading(id=indicator_id, cls="htmx-indicator ml-2")
