"""Service functions for fetching and cleaning HTML content from webpages."""

import logging

import html2text
import httpx

logger = logging.getLogger(__name__)


def create_html_cleaner() -> html2text.HTML2Text:
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.body_width = 0  # Prevents wrapping
    return h


def clean_html_text(html_text: str) -> str:
    """Cleans raw HTML text and returns plain text."""
    cleaner = create_html_cleaner()
    return cleaner.handle(html_text)


async def fetch_page_text(recipe_url: str) -> str:
    """Fetches the raw text content of a webpage."""
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
            f"Error fetching page text from {recipe_url}: {e!r}", exc_info=True
        )
        raise


async def fetch_and_clean_text_from_url(url: str) -> str:
    """Fetches and cleans HTML from a URL, returning plain text."""
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
