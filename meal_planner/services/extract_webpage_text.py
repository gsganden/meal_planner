"""Web page content extraction service for the Meal Planner application."""

import logging

import html2text
import httpx

logger = logging.getLogger(__name__)


async def fetch_and_clean_text_from_url(url: str) -> str:
    """Fetch and process a webpage into clean text for recipe extraction.

    Combines fetching and cleaning operations to provide a single entry point
    for webpage processing. Includes comprehensive error handling and logging
    for debugging failed extractions.

    Args:
        url: URL of the recipe webpage to process.

    Returns:
        Clean plain text extracted from the webpage, suitable for
        LLM processing.

    Raises:
        httpx.RequestError: For network issues during fetching.
        httpx.HTTPStatusError: For HTTP error responses.
        RuntimeError: For failures in fetching or processing with context.
    """
    logger.info(f"Fetching text from: {url}")
    try:
        raw_text = await fetch_page_text(url)
        logger.info(f"Successfully fetched text from: {url}")
    except httpx.RequestError as e:
        logger.error(
            f"HTTP Request Error fetching page text from {url}: {e!r}",
            exc_info=True,
        )
        raise
    except httpx.HTTPStatusError as e:
        logger.error(
            f"HTTP Status Error fetching page text from {url}: {e!r}",
            exc_info=True,
        )
        raise
    except Exception as e:
        logger.error(
            f"Generic error fetching page text from {url}: {e!r}", exc_info=True
        )
        raise RuntimeError(f"Failed to fetch or process URL: {url}") from e

    try:
        page_text = clean_html_text(raw_text)
        logger.info(f"Cleaned HTML text from: {url}")
        return page_text
    except Exception as e:
        logger.error(f"Error cleaning HTML text from {url}: {e!r}", exc_info=True)
        raise RuntimeError(f"Failed to process URL content: {url}") from e


async def fetch_page_text(recipe_url: str) -> str:
    """Fetch the raw HTML content from a recipe URL.

    Makes an HTTP GET request with browser-like headers to avoid blocking
    by recipe websites. Handles redirects and enforces reasonable timeouts.

    Args:
        recipe_url: URL of the recipe webpage to fetch.

    Returns:
        Raw HTML text of the webpage.

    Raises:
        httpx.RequestError: For network-related errors.
        httpx.HTTPStatusError: For non-2xx HTTP responses.
        Exception: For other unexpected errors during fetching.
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
                "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        }
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=15.0, headers=headers
        ) as client:
            response = await client.get(recipe_url)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.error(
            "Error fetching page text from %s: %r", recipe_url, e, exc_info=True
        )
        raise


def clean_html_text(html_text: str) -> str:
    """Convert raw HTML to clean plain text format.

    Processes HTML content through the configured HTML2Text converter,
    removing formatting, links, and images while preserving text structure
    and readability.

    Args:
        html_text: Raw HTML string to clean.

    Returns:
        Plain text representation of the HTML content suitable for
        recipe extraction by the LLM.
    """

    def _create_html_cleaner() -> html2text.HTML2Text:
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True
        h.body_width = 0  # Prevents wrapping
        return h

    cleaner = _create_html_cleaner()
    return cleaner.handle(html_text)
