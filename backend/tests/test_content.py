import pytest

from app.services.content import extract_content


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Article</title></head>
<body>
<nav>Navigation links here</nav>
<article>
<h1>Understanding Vector Databases</h1>
<p>Vector databases are specialized systems designed to store and query
high-dimensional vectors efficiently. They power modern semantic search,
recommendation engines, and AI applications.</p>
<p>Unlike traditional databases that match on exact values, vector databases
find the nearest neighbors in embedding space. This enables similarity-based
retrieval that understands meaning rather than just keywords.</p>
<p>Popular options include pgvector for PostgreSQL, Pinecone, and Weaviate.
Each offers different trade-offs between scalability, cost, and ease of use.</p>
</article>
<footer>Copyright 2026</footer>
</body>
</html>
"""


def test_extract_content_returns_text():
    text = extract_content(SAMPLE_HTML)
    assert text is not None
    assert len(text) > 50
    assert "vector databases" in text.lower()


def test_extract_content_strips_nav_and_footer():
    text = extract_content(SAMPLE_HTML)
    assert "Navigation links here" not in text
    assert "Copyright 2026" not in text


def test_extract_content_empty_html_returns_none():
    result = extract_content("")
    assert result is None


def test_extract_content_no_article_returns_none():
    result = extract_content("<html><body></body></html>")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_and_extract_with_url(monkeypatch):
    """Test the async fetch_content function with a mocked HTTP call."""
    import httpx
    from app.services.content import fetch_content

    async def mock_get(self, url, **kwargs):
        response = httpx.Response(200, text=SAMPLE_HTML, request=httpx.Request("GET", url))
        return response

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    text = await fetch_content("https://example.com/article")
    assert text is not None
    assert "vector databases" in text.lower()


@pytest.mark.asyncio
async def test_fetch_content_handles_http_error(monkeypatch):
    """Test that fetch_content returns None on HTTP errors."""
    import httpx
    from app.services.content import fetch_content

    async def mock_get(self, url, **kwargs):
        raise httpx.HTTPStatusError(
            "Not Found",
            request=httpx.Request("GET", url),
            response=httpx.Response(404),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    result = await fetch_content("https://example.com/missing")
    assert result is None
