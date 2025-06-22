"""Routers for generating and returning HTML UI fragments, often for HTMX swaps."""

import ipaddress
import logging
from urllib.parse import urlparse

import httpx
from fastapi import Request
from fasthtml.common import *
from monsterui.all import TextArea
from pydantic import ValidationError
from starlette.datastructures import FormData

from meal_planner.core import rt
from meal_planner.form_processing import parse_recipe_form_data
from meal_planner.models import MakesRangeValidationError, RecipeBase
from meal_planner.services.extract_webpage_text import (
    fetch_and_clean_text_from_url,
)
from meal_planner.ui.common import CSS_ERROR_CLASS
from meal_planner.ui.edit_recipe import (
    build_diff_content_children,
    build_makes_section,
    render_ingredient_list_items,
    render_instruction_list_items,
)

logger = logging.getLogger(__name__)


def _validate_url_for_ssrf(url: str) -> tuple[bool, str]:
    """Validate URL to prevent SSRF attacks.

    Checks for:
    - Valid HTTP/HTTPS scheme
    - Non-empty domain
    - Blocks private IP ranges and localhost

    Args:
        url: The URL to validate

    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return False, "Only HTTP and HTTPS URLs are allowed"

        if not parsed.netloc:
            return False, "Invalid URL: missing domain"

        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid URL: could not extract hostname"

        ip = _try_parse_ip(hostname)
        if ip:
            if ip.is_loopback:
                return False, "Loopback addresses are not allowed"

            if ip.is_link_local:
                return False, "Link-local addresses are not allowed"

            if ip.is_multicast:
                return False, "Multicast addresses are not allowed"

            if ip.is_private:
                return False, "Private IP addresses are not allowed"
        else:
            internal_hostnames = {
                "localhost",
                "localhost.localdomain",
                "metadata",
                "metadata.google.internal",
                "instance-data",
                "link-local",
            }
            if hostname.lower() in internal_hostnames:
                return False, "Internal hostnames are not allowed"

        return True, ""

    except Exception as e:
        logger.warning("URL validation error for %s: %s", url, e)
        return False, "Invalid URL format"


def _try_parse_ip(
    hostname: str,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Attempt to parse a hostname as an IP address.

    Args:
        hostname: The hostname string to parse.

    Returns:
        An ipaddress object if parsing succeeds, otherwise None.
    """
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        return None


async def _delete_list_item(request: Request, index: int, item_type: str) -> FT:
    """Delete an item from a recipe list and return updated UI components.

    Handles deletion of ingredients or instructions from the recipe form,
    maintaining form state and updating the diff view.

    Args:
        request: FastAPI request containing form data.
        index: Zero-based index of the item to delete.
        item_type: Either "ingredients" or "instructions".

    Returns:
        Updated list component with diff view via OOB swap.
        On error, returns an error message in place of the list.
    """
    form_data = await request.form()
    list_id = f"{item_type}-list"
    render_func = (
        render_ingredient_list_items
        if item_type == "ingredients"
        else render_instruction_list_items
    )

    try:
        parsed_data = parse_recipe_form_data(form_data)
        current_items = parsed_data.get(item_type, [])

        if 0 <= index < len(current_items):
            del current_items[index]
        else:
            logger.warning(
                f"Attempted to delete {item_type[:-1]} at invalid index {index}"
            )

        parsed_data[item_type] = current_items
        new_current_recipe = RecipeBase(**parsed_data)

        original_data = parse_recipe_form_data(form_data, prefix="original_")
        original_recipe = RecipeBase(**original_data)

        new_item_components = render_func(getattr(new_current_recipe, item_type))
        return _build_sortable_list_with_oob_diff(
            list_id=list_id,
            rendered_list_items=new_item_components,
            original_recipe=original_recipe,
            current_recipe=new_current_recipe,
        )

    except ValidationError as e:
        logger.error(
            f"Validation error processing {item_type[:-1]} deletion at index {index}: "
            f"{e}",
            exc_info=True,
        )
        data_for_error_render = parse_recipe_form_data(form_data)
        items_for_error_render = data_for_error_render.get(item_type, [])

        error_items_list = render_func(items_for_error_render)
        items_list_component = Div(
            P(
                "Error updating list after delete. Validation failed.",
                cls=CSS_ERROR_CLASS,
            ),
            *error_items_list,
            id=list_id,
            cls="mb-4",
        )
        return items_list_component

    except Exception as e:
        logger.error(
            f"Error deleting {item_type[:-1]} at index {index}: {e}", exc_info=True
        )
        return Div(
            "Error processing delete request.",
            cls=CSS_ERROR_CLASS,
            id=list_id,
        )


@rt("/recipes/ui/delete-ingredient/{index:int}")
async def post_delete_ingredient_row(request: Request, index: int):
    """Delete a specific ingredient from the recipe form.

    HTMX endpoint for removing an ingredient at the specified index.
    Updates both the ingredient list and the diff view.

    Args:
        request: FastAPI request with current form state.
        index: Zero-based position of ingredient to delete.

    Returns:
        Updated ingredient list HTML with OOB diff update.
    """
    return await _delete_list_item(request, index, "ingredients")


@rt("/recipes/ui/delete-instruction/{index:int}")
async def post_delete_instruction_row(request: Request, index: int):
    """Delete a specific instruction from the recipe form.

    HTMX endpoint for removing an instruction at the specified index.
    Updates both the instruction list and the diff view.

    Args:
        request: FastAPI request with current form state.
        index: Zero-based position of instruction to delete.

    Returns:
        Updated instruction list HTML with OOB diff update.
    """
    return await _delete_list_item(request, index, "instructions")


async def _add_list_item(request: Request, item_type: str) -> FT:
    """Add a new empty item to a recipe list and return updated UI components.

    Handles addition of new ingredients or instructions to the recipe form,
    adding an empty field that the user can populate.

    Args:
        request: FastAPI request containing form data.
        item_type: Either "ingredients" or "instructions".

    Returns:
        Updated list component with a new empty item and diff view update.
        On error, returns an error message in place of the list.
    """
    form_data = await request.form()
    list_id = f"{item_type}-list"
    render_func = (
        render_ingredient_list_items
        if item_type == "ingredients"
        else render_instruction_list_items
    )

    try:
        parsed_data = parse_recipe_form_data(form_data)
        current_items = parsed_data.get(item_type, [])
        current_items.append("")

        parsed_data[item_type] = current_items
        new_current_recipe = RecipeBase(**parsed_data)

        original_data = parse_recipe_form_data(form_data, prefix="original_")
        original_recipe = RecipeBase(**original_data)

        new_item_components = render_func(getattr(new_current_recipe, item_type))
        return _build_sortable_list_with_oob_diff(
            list_id=list_id,
            rendered_list_items=new_item_components,
            original_recipe=original_recipe,
            current_recipe=new_current_recipe,
        )

    except ValidationError as e:
        logger.error(
            f"Validation error processing {item_type[:-1]} addition: {e}", exc_info=True
        )
        items_before_error = parse_recipe_form_data(form_data).get(item_type, [])
        error_items = render_func(items_before_error)
        return Div(
            P("Error updating list after add.", cls=CSS_ERROR_CLASS),
            *error_items,
            id=list_id,
            cls="mb-4",
        )
    except Exception as e:
        logger.error(f"Error adding {item_type[:-1]}: {e}", exc_info=True)
        return Div("Error processing add request.", cls=CSS_ERROR_CLASS, id=list_id)


@rt("/recipes/ui/add-ingredient")
async def post_add_ingredient_row(request: Request):
    """Add a new empty ingredient field to the recipe form.

    HTMX endpoint that appends a blank ingredient input to the list,
    allowing users to add more ingredients to their recipe.

    Args:
        request: FastAPI request with current form state.

    Returns:
        Updated ingredient list HTML with new field and OOB diff update.
    """
    return await _add_list_item(request, "ingredients")


@rt("/recipes/ui/add-instruction")
async def post_add_instruction_row(request: Request):
    """Add a new empty instruction field to the recipe form.

    HTMX endpoint that appends a blank instruction textarea to the list,
    allowing users to add more steps to their recipe.

    Args:
        request: FastAPI request with current form state.

    Returns:
        Updated instruction list HTML with new field and OOB diff update.
    """
    return await _add_list_item(request, "instructions")


@rt("/recipes/ui/update-diff")
async def update_diff(request: Request) -> FT:
    """Update the diff view based on current form data.

    Recalculates the before/after comparison between the original recipe
    and current edits. Called when form fields change or items are reordered.

    Args:
        request: FastAPI request containing both current and original recipe data.

    Returns:
        Updated diff view showing changes, or error message on validation failure.
    """
    form_data = await request.form()
    try:
        current_data = parse_recipe_form_data(form_data)
        original_data = parse_recipe_form_data(form_data, prefix="original_")
        current_recipe = RecipeBase(**current_data)
        original_recipe = RecipeBase(**original_data)

        before_component, after_component = build_diff_content_children(
            original_recipe, current_recipe.markdown
        )
        return Div(
            before_component,
            after_component,
            cls="flex space-x-4 mt-4",
            id="diff-content-wrapper",
        )
    except ValidationError as e:
        for error in e.errors():
            if isinstance(error.get("ctx", {}).get("error"), MakesRangeValidationError):
                current_data = parse_recipe_form_data(form_data)
                makes_min_str = current_data.get("makes_min")
                makes_max_str = current_data.get("makes_max")
                makes_unit = current_data.get("makes_unit")

                makes_min = int(makes_min_str) if makes_min_str else None
                makes_max = int(makes_max_str) if makes_max_str else None

                makes_section_with_error = build_makes_section(
                    makes_min,
                    makes_max,
                    makes_unit,
                    error_message="Max quantity cannot be less than min quantity",
                )

                return Group(
                    makes_section_with_error,
                    hx_swap_oob="outerHTML:#makes-section",
                )

        logger.warning("Validation error during diff update: %s", e, exc_info=False)
        error_message = "Please check your recipe fields - there may be invalid values."
        return Div(error_message, cls=CSS_ERROR_CLASS)
    except Exception as e:
        logger.error("Error updating diff: %s", e, exc_info=True)
        return Div("Error updating diff view.", cls=CSS_ERROR_CLASS)


@rt("/recipes/ui/fetch-text")
async def post_fetch_text(request: Request):
    """Fetch and clean text content from a recipe URL.

    HTMX endpoint that retrieves webpage content, cleans it, and populates
    the recipe text area. Handles various error cases with appropriate messages.

    Args:
        request: FastAPI request containing form data with input_url.

    Returns:
        Group containing updated textarea with fetched content and
        error/success messages via OOB swap.
    """
    form_data = await request.form()
    input_url = form_data.get("input_url")

    def _prepare_error_response(error_message_str: str):
        """Prepare error response with textarea and error message."""
        error_div = Div(
            error_message_str, cls=CSS_ERROR_CLASS, id="fetch-url-error-display"
        )
        error_oob = Div(error_div, hx_swap_oob="outerHTML:#fetch-url-error-display")
        text_area = Div(
            TextArea(
                id="recipe_text",
                name="recipe_text",
                placeholder="Paste full recipe text here, or fetch from URL above.",
                rows=15,
                cls="mb-4",
            ),
            id="recipe_text_container",
        )
        return Group(text_area, error_oob)

    if not input_url:
        logger.error("Fetch text called without URL.")
        return _prepare_error_response("Please provide a Recipe URL to fetch.")

    # Validate URL to prevent SSRF attacks
    is_valid, error_message = _validate_url_for_ssrf(input_url)
    if not is_valid:
        logger.warning(
            "Blocked potentially unsafe URL: %s - %s", input_url, error_message
        )
        return _prepare_error_response(f"Invalid URL: {error_message}")

    try:
        logger.info("Fetching and cleaning text from URL: %s", input_url)
        cleaned_text = await fetch_and_clean_text_from_url(input_url)
    except httpx.RequestError as e:
        logger.error("Network error fetching URL %s: %s", input_url, e, exc_info=True)
        result = _prepare_error_response(
            "Error fetching URL. Please check the URL and your connection."
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP error fetching URL %s: Status %s. Response: %s",
            input_url,
            e.response.status_code,
            e.response.text,
            exc_info=True,
        )
        result = _prepare_error_response(
            _get_http_error_message(e.response.status_code, e.response.text)
        )
    except RuntimeError as e:
        logger.error(
            "RuntimeError processing URL content from %s: %s",
            input_url,
            e,
            exc_info=True,
        )
        result = _prepare_error_response("Failed to process the content from the URL.")
    except Exception as e:
        logger.error(
            "Unexpected error fetching text from %s: %s", input_url, e, exc_info=True
        )
        result = _prepare_error_response(
            "An unexpected error occurred while fetching text."
        )
    else:
        text_area = Div(
            TextArea(
                cleaned_text,
                id="recipe_text",
                name="recipe_text",
                placeholder="Paste full recipe text here, or fetch from URL above.",
                rows=15,
                cls="mb-4",
            ),
            id="recipe_text_container",
        )
        clear_error_oob = Div(
            Div(id="fetch-url-error-display"),
            hx_swap_oob="outerHTML:#fetch-url-error-display",
        )
        result = Group(text_area, clear_error_oob)

    return result


def _get_http_error_message(status_code: int, response_text: str = "") -> str:
    """Generate user-friendly error messages for HTTP status codes.

    Analyzes the HTTP status code and response content to provide specific,
    actionable error messages that help users understand whether the issue
    is with the website's compatibility or our service.

    Args:
        status_code: HTTP response status code.
        response_text: Response body text to analyze for specific error patterns.

    Returns:
        User-friendly error message explaining the issue and next steps.
    """
    if any(
        indicator in response_text.lower()
        for indicator in (
            "perimeterx",
            "cloudflare",
            "automation tools",
            "verify you are a human",
            "access denied",
            "blocked",
            "captcha",
            "bot detection",
            "security check",
        )
    ):
        result = (
            "This website uses security measures that block automated access. "
            "You can copy and paste the recipe text below instead."
        )
    elif 400 <= status_code < 600:
        result = {
            401: (
                "This website requires login to access recipes. "
                "You can copy and paste the recipe text below instead."
            ),
            403: (
                "This website doesn't allow automated access to its content. "
                "You can copy and paste the recipe text below instead."
            ),
            404: "The recipe page was not found. Please check the URL and try again.",
            429: (
                "This website is limiting requests. Please wait a few minutes and "
                "try again, or copy and paste the recipe text below instead."
            ),
            500: (
                "The website is currently experiencing server issues. "
                "Please try again later or copy and paste the recipe text below "
                "instead."
            ),
            502: (
                "The website is currently experiencing server issues. "
                "Please try again later or copy and paste the recipe text below."
            ),
            503: (
                "The website is currently experiencing server issues. "
                "Please try again later or copy and paste the recipe text below "
                "instead."
            ),
            504: (
                "The website is currently experiencing server issues. "
                "Please try again later or copy and paste the recipe text below "
                "instead."
            ),
        }.get(
            status_code,
            "This website doesn't allow our recipe fetcher to access its content. "
            "You can copy and paste the recipe text below instead.",
        )
    else:
        result = "Error fetching URL: The server returned an error."

    return result


def _build_sortable_list_with_oob_diff(
    list_id: str,
    rendered_list_items: list[FT],
    original_recipe: RecipeBase,
    current_recipe: RecipeBase,
) -> FT:
    """Build a sortable list component with an out-of-band diff update.

    Creates a draggable/sortable list of recipe items that triggers diff
    updates when reordered. Includes OOB swap for updating the diff view
    without replacing the list itself.

    Args:
        list_id: The HTML ID for the list container (e.g., "ingredients-list").
        rendered_list_items: List of FastHTML components representing the items.
        original_recipe: The baseline recipe for the diff comparison.
        current_recipe: The current state of the recipe for the diff.

    Returns:
        Group containing the sortable list and OOB diff update components.
    """
    list_component = Div(
        *rendered_list_items,
        id=list_id,
        cls="mb-4",
        uk_sortable="handle: .drag-handle",
        hx_trigger="moved",
        hx_post="/recipes/ui/update-diff",
        hx_target="#diff-content-wrapper",
        hx_swap="innerHTML",
        hx_include="closest form",
    )

    before_notstr, after_notstr = build_diff_content_children(
        original_recipe, current_recipe.markdown
    )
    oob_diff_component = Div(
        before_notstr,
        after_notstr,
        hx_swap_oob="innerHTML:#diff-content-wrapper",
    )
    return Group(list_component, oob_diff_component)


def _adjust_makes_values(
    makes_min: int | None,
    makes_max: int | None,
    changed: str | None,
    form_data: FormData,
) -> tuple[int | None, int | None]:
    """Adjust min/max values to ensure valid range."""
    if makes_min is None or makes_max is None or makes_min <= makes_max:
        return makes_min, makes_max

    if changed == "min":
        return makes_min, makes_min
    elif changed == "max":
        return makes_max, makes_max
    else:
        original_data = parse_recipe_form_data(form_data, prefix="original_")
        original_min_str = original_data.get("makes_min")
        original_min = int(original_min_str) if original_min_str else None

        if original_min != makes_min:
            return makes_min, makes_min
        else:
            return makes_max, makes_max


def _build_diff_oob_component(
    original_recipe: RecipeBase, current_recipe: RecipeBase
) -> FT:
    """Build out-of-band diff component for HTMX updates."""
    before_component, after_component = build_diff_content_children(
        original_recipe, current_recipe.markdown
    )
    return Div(
        before_component,
        after_component,
        cls="flex space-x-4 mt-4",
        hx_swap_oob="innerHTML:#diff-content-wrapper",
    )


@rt("/recipes/ui/adjust-makes")
async def adjust_makes(request: Request, changed: str | None = None) -> FT:
    """Adjust makes range to prevent invalid states and update diff.

    When a user changes min or max makes, this endpoint automatically
    adjusts the other value if needed to maintain a valid range, then
    returns the updated makes section with OOB diff update.

    Args:
        request: FastAPI request containing form data with makes values.
        changed: Which field was changed ('min' or 'max'). If not provided,
            the function will infer which field changed by comparing with
            original values for backward compatibility.

    Returns:
        Updated makes section with adjusted values and OOB diff update.
    """
    form_data = await request.form()

    try:
        current_data = parse_recipe_form_data(form_data)
    except Exception as e:
        logger.error("Error parsing form data: %s", e, exc_info=True)
        return build_makes_section(None, None, None)

    makes_min_str = current_data.get("makes_min")
    makes_max_str = current_data.get("makes_max")
    makes_unit = current_data.get("makes_unit")

    makes_min = int(makes_min_str) if makes_min_str else None
    makes_max = int(makes_max_str) if makes_max_str else None

    makes_min, makes_max = _adjust_makes_values(
        makes_min, makes_max, changed, form_data
    )

    current_data["makes_min"] = makes_min
    current_data["makes_max"] = makes_max
    current_data["makes_unit"] = makes_unit

    try:
        original_data = parse_recipe_form_data(form_data, prefix="original_")
        current_recipe = RecipeBase(**current_data)
        original_recipe = RecipeBase(**original_data)
    except ValidationError as e:
        logger.warning(
            "Validation error during makes adjustment: %s", e, exc_info=False
        )
        return build_makes_section(
            makes_min,
            makes_max,
            makes_unit,
            error_message="Please enter valid makes numbers",
        )

    updated_makes_section = build_makes_section(makes_min, makes_max, makes_unit)

    try:
        oob_diff_component = _build_diff_oob_component(original_recipe, current_recipe)
        return Group(updated_makes_section, oob_diff_component)
    except Exception as e:
        logger.error("Error building diff component: %s", e, exc_info=True)
        return updated_makes_section
