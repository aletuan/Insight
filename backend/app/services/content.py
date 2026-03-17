"""
Content extraction service.

Fetches a URL and extracts the main article text using trafilatura.
Falls back to None if extraction fails or content is empty.
"""
import logging

import httpx
import trafilatura

logger = logging.getLogger(__name__)


def extract_content(html: str) -> str | None:
    """Extract main article text from raw HTML using trafilatura.

    Args:
        html: Raw HTML string.

    Returns:
        Extracted text, or None if extraction fails or result is empty.
    """
    if not html or not html.strip():
        return None

    text = trafilatura.extract(html, include_comments=False, include_tables=False)

    if not text or len(text.strip()) < 20:
        return None

    return text.strip()


async def fetch_content(url: str) -> str | None:
    """Fetch a URL and extract its main content.

    Args:
        url: The URL to fetch.

    Returns:
        Extracted article text, or None on failure.
    """
    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Insight/1.0 (personal knowledge digest)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text
    except (httpx.HTTPError, httpx.HTTPStatusError) as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None

    return extract_content(html)
