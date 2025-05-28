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
    return Loading(id=indicator_id, cls="htmx-indicator ml-2")
