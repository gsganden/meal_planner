from fasthtml.common import *
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


def create_add_item_button(hx_post_url: str, hx_target_selector: str) -> Button:
    """
    Creates a standardized 'add item' button.

    Args:
        hx_post_url: The URL for the HX-Post attribute.
        hx_target_selector: The CSS selector for the HX-Target attribute (e.g.,
            '#my-list').
    """
    return Button(
        ICON_ADD,
        hx_post=hx_post_url,
        hx_target=hx_target_selector,
        hx_swap="innerHTML",
        hx_include="closest form",
        cls="mb-4 uk-border-circle p-1 flex items-center justify-center",
    )
