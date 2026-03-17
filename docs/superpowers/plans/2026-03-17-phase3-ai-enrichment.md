# Phase 3: AI Enrichment Pipeline

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich every ingested item with full-text content extraction, AI-generated summaries and topic tags, and vector embeddings — enabling semantic search across the knowledge base.

**Architecture:** On item ingest, an asyncio background task extracts page content via trafilatura, generates a 3-4 sentence summary + topic tags via Claude Haiku (structured JSON output), embeds title+summary via OpenAI text-embedding-3-small (1536 dims), and updates the item record. Items follow a lifecycle: pending → enriching → enriched → failed. On startup, the app sweeps for stuck/failed items and re-queues them.

**Tech Stack:** trafilatura (content extraction), Anthropic Claude Haiku (summarization + tagging), OpenAI text-embedding-3-small (embeddings), asyncio (background worker), pgvector cosine similarity (semantic search)

**Spec:** `docs/superpowers/specs/2026-03-17-personal-knowledge-digest-design.md`

---

### Task 1: Content extraction service

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/content.py`
- Create: `backend/tests/test_content.py`

- [ ] **Step 1: Write failing tests for content extraction**

```python
# backend/tests/test_content.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_content.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services'`

- [ ] **Step 3: Create services package and content.py**

```python
# backend/app/services/__init__.py
```

```python
# backend/app/services/content.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/test_content.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ backend/tests/test_content.py
git commit -m "feat: add content extraction service with trafilatura"
```

---

### Task 2: Haiku summarization service

**Files:**
- Create: `backend/app/services/enrichment.py`
- Create: `backend/tests/test_enrichment.py`

- [ ] **Step 1: Write failing tests for summarization**

```python
# backend/tests/test_enrichment.py
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.enrichment import summarize_content, generate_embedding


SAMPLE_TEXT = (
    "Vector databases are specialized systems designed to store and query "
    "high-dimensional vectors efficiently. They power modern semantic search, "
    "recommendation engines, and AI applications. Unlike traditional databases "
    "that match on exact values, vector databases find the nearest neighbors "
    "in embedding space. This enables similarity-based retrieval that understands "
    "meaning rather than just keywords."
)


class MockAnthropicMessage:
    """Mock Anthropic API response."""

    def __init__(self, text: str):
        self.content = [MagicMock(text=text)]


@pytest.mark.asyncio
async def test_summarize_content_returns_summary_and_tags():
    mock_response = MockAnthropicMessage(json.dumps({
        "summary": "Vector databases store high-dimensional vectors for efficient similarity search. They power semantic search and AI applications by finding nearest neighbors in embedding space. This approach understands meaning rather than relying on exact keyword matches.",
        "tags": ["vector-databases", "semantic-search", "embeddings", "AI"]
    }))

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("app.services.enrichment.get_anthropic_client", return_value=mock_client):
        result = await summarize_content("Test Article", SAMPLE_TEXT)

    assert result is not None
    summary, tags = result
    assert len(summary) > 20
    assert isinstance(tags, list)
    assert len(tags) >= 1


@pytest.mark.asyncio
async def test_summarize_content_title_only_when_no_content():
    mock_response = MockAnthropicMessage(json.dumps({
        "summary": "An article about vector databases and their applications.",
        "tags": ["vector-databases"]
    }))

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("app.services.enrichment.get_anthropic_client", return_value=mock_client):
        result = await summarize_content("Understanding Vector Databases", None)

    assert result is not None
    summary, tags = result
    assert len(summary) > 10


@pytest.mark.asyncio
async def test_summarize_content_returns_none_on_api_error():
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("API rate limit"))

    with patch("app.services.enrichment.get_anthropic_client", return_value=mock_client):
        result = await summarize_content("Test", SAMPLE_TEXT)

    assert result is None


@pytest.mark.asyncio
async def test_summarize_content_returns_none_on_invalid_json():
    mock_response = MockAnthropicMessage("This is not valid JSON")

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("app.services.enrichment.get_anthropic_client", return_value=mock_client):
        result = await summarize_content("Test", SAMPLE_TEXT)

    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_enrichment.py::test_summarize_content_returns_summary_and_tags -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.enrichment'`

- [ ] **Step 3: Create enrichment.py with summarize_content**

```python
# backend/app/services/enrichment.py
"""
AI enrichment service.

Provides summarization (Claude Haiku) and embedding (OpenAI) for ingested items.
"""
import json
import logging

import anthropic
import openai

from app.config import settings

logger = logging.getLogger(__name__)

SUMMARIZE_SYSTEM_PROMPT = """You are a concise research assistant. Given an article title and optionally its full text, produce a JSON object with exactly two keys:

- "summary": A 3-4 sentence summary of the content. Focus on the key ideas and why they matter. If only a title is provided (no content), write a brief 1-2 sentence description based on the title alone.
- "tags": An array of 2-5 lowercase topic tags (e.g. "machine-learning", "web-development", "startup-strategy"). Use hyphens for multi-word tags.

Respond with ONLY valid JSON, no markdown fences or extra text."""


def get_anthropic_client():
    """Return an async Anthropic client. Separated for easy mocking."""
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


def get_openai_client():
    """Return an async OpenAI client. Separated for easy mocking."""
    return openai.AsyncOpenAI(api_key=settings.openai_api_key)


async def summarize_content(title: str, content: str | None) -> tuple[str, list[str]] | None:
    """Generate a summary and topic tags using Claude Haiku.

    Args:
        title: The item title.
        content: The extracted article text, or None if extraction failed.

    Returns:
        Tuple of (summary, tags) on success, or None on failure.
    """
    if content:
        user_message = f"Title: {title}\n\nContent:\n{content[:8000]}"
    else:
        user_message = f"Title: {title}\n\n(No article content available — summarize based on title only)"

    try:
        client = get_anthropic_client()
        message = await client.messages.create(
            model="claude-haiku-4-20250414",
            max_tokens=512,
            system=SUMMARIZE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw_text = message.content[0].text
        parsed = json.loads(raw_text)

        summary = parsed.get("summary", "")
        tags = parsed.get("tags", [])

        if not summary:
            logger.warning("Haiku returned empty summary")
            return None

        return summary, tags

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse Haiku JSON response: {e}")
        return None
    except Exception as e:
        logger.warning(f"Haiku summarization failed: {e}")
        return None


async def generate_embedding(text: str) -> list[float] | None:
    """Generate a 1536-dim embedding using OpenAI text-embedding-3-small.

    Args:
        text: The text to embed (typically title + summary).

    Returns:
        List of 1536 floats, or None on failure.
    """
    try:
        client = get_openai_client()
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000],
        )
        embedding = response.data[0].embedding
        return embedding

    except Exception as e:
        logger.warning(f"OpenAI embedding failed: {e}")
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/test_enrichment.py -k "summarize" -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/enrichment.py backend/tests/test_enrichment.py
git commit -m "feat: add Haiku summarization service with structured JSON output"
```

---

### Task 3: OpenAI embedding service

**Files:**
- Modify: `backend/tests/test_enrichment.py`
- (enrichment.py already has `generate_embedding` from Task 2)

- [ ] **Step 1: Add embedding tests to test_enrichment.py**

Append to `backend/tests/test_enrichment.py`:

```python
class MockEmbeddingData:
    """Mock OpenAI embedding response."""

    def __init__(self, embedding: list[float]):
        self.embedding = embedding


class MockEmbeddingResponse:
    """Mock OpenAI embeddings.create response."""

    def __init__(self, embedding: list[float]):
        self.data = [MockEmbeddingData(embedding)]


@pytest.mark.asyncio
async def test_generate_embedding_returns_vector():
    fake_embedding = [0.1] * 1536

    mock_client = AsyncMock()
    mock_client.embeddings.create = AsyncMock(
        return_value=MockEmbeddingResponse(fake_embedding)
    )

    with patch("app.services.enrichment.get_openai_client", return_value=mock_client):
        result = await generate_embedding("Test article about vector databases")

    assert result is not None
    assert len(result) == 1536
    assert result[0] == 0.1


@pytest.mark.asyncio
async def test_generate_embedding_returns_none_on_error():
    mock_client = AsyncMock()
    mock_client.embeddings.create = AsyncMock(side_effect=Exception("API error"))

    with patch("app.services.enrichment.get_openai_client", return_value=mock_client):
        result = await generate_embedding("Test text")

    assert result is None


@pytest.mark.asyncio
async def test_generate_embedding_truncates_long_input():
    """Verify that very long input doesn't cause errors (truncated to 8000 chars)."""
    long_text = "word " * 5000  # 25000 chars
    fake_embedding = [0.5] * 1536

    mock_client = AsyncMock()
    mock_client.embeddings.create = AsyncMock(
        return_value=MockEmbeddingResponse(fake_embedding)
    )

    with patch("app.services.enrichment.get_openai_client", return_value=mock_client):
        result = await generate_embedding(long_text)

    assert result is not None
    assert len(result) == 1536
    # Verify the API was called with truncated input
    call_args = mock_client.embeddings.create.call_args
    assert len(call_args.kwargs["input"]) <= 8000
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/test_enrichment.py -v
```

Expected: 7 passed (4 summarize + 3 embedding)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_enrichment.py
git commit -m "feat: add OpenAI embedding service with tests"
```

---

### Task 4: Background enrichment worker

**Files:**
- Create: `backend/app/services/worker.py`
- Create: `backend/tests/test_worker.py`

- [ ] **Step 1: Write failing tests for the enrichment worker**

```python
# backend/tests/test_worker.py
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base, Item, ItemStatus, SourceType
from app.services.worker import enrich_item

TEST_DATABASE_URL = settings.database_url.replace("/insight", "/insight_test")
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session():
    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def pending_item(db_session):
    item = Item(
        id=uuid.uuid4(),
        url="https://example.com/test-article",
        title="Test Article About AI",
        source=SourceType.chrome,
        status=ItemStatus.pending,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


@pytest.mark.asyncio
async def test_enrich_item_success(pending_item):
    """Full enrichment pipeline: fetch → summarize → embed → update DB."""
    fake_embedding = [0.1] * 1536

    with (
        patch("app.services.worker.fetch_content", new_callable=AsyncMock) as mock_fetch,
        patch("app.services.worker.summarize_content", new_callable=AsyncMock) as mock_summarize,
        patch("app.services.worker.generate_embedding", new_callable=AsyncMock) as mock_embed,
    ):
        mock_fetch.return_value = "Full article text about AI and machine learning."
        mock_summarize.return_value = (
            "This article discusses AI and machine learning advances.",
            ["ai", "machine-learning"],
        )
        mock_embed.return_value = fake_embedding

        await enrich_item(pending_item.id, TEST_DATABASE_URL)

    # Verify DB state
    async with TestSession() as session:
        result = await session.execute(select(Item).where(Item.id == pending_item.id))
        item = result.scalar_one()
        assert item.status == ItemStatus.enriched
        assert item.summary == "This article discusses AI and machine learning advances."
        assert item.tags == ["ai", "machine-learning"]
        assert item.raw_content == "Full article text about AI and machine learning."
        assert item.embedding is not None
        assert item.processed_at is not None


@pytest.mark.asyncio
async def test_enrich_item_content_fetch_fails_still_enriches(pending_item):
    """If content extraction fails, still summarize from title only."""
    fake_embedding = [0.2] * 1536

    with (
        patch("app.services.worker.fetch_content", new_callable=AsyncMock) as mock_fetch,
        patch("app.services.worker.summarize_content", new_callable=AsyncMock) as mock_summarize,
        patch("app.services.worker.generate_embedding", new_callable=AsyncMock) as mock_embed,
    ):
        mock_fetch.return_value = None  # Content extraction failed
        mock_summarize.return_value = (
            "An article about AI based on its title.",
            ["ai", "content_failed"],
        )
        mock_embed.return_value = fake_embedding

        await enrich_item(pending_item.id, TEST_DATABASE_URL)

    async with TestSession() as session:
        result = await session.execute(select(Item).where(Item.id == pending_item.id))
        item = result.scalar_one()
        assert item.status == ItemStatus.enriched
        assert "content_failed" in item.tags


@pytest.mark.asyncio
async def test_enrich_item_summarization_fails_marks_failed(pending_item):
    """If summarization fails after retries, item is marked as failed."""
    with (
        patch("app.services.worker.fetch_content", new_callable=AsyncMock) as mock_fetch,
        patch("app.services.worker.summarize_content", new_callable=AsyncMock) as mock_summarize,
    ):
        mock_fetch.return_value = "Some content"
        mock_summarize.return_value = None  # Summarization failed

        await enrich_item(pending_item.id, TEST_DATABASE_URL)

    async with TestSession() as session:
        result = await session.execute(select(Item).where(Item.id == pending_item.id))
        item = result.scalar_one()
        assert item.status == ItemStatus.failed


@pytest.mark.asyncio
async def test_enrich_item_embedding_fails_marks_failed(pending_item):
    """If embedding fails after retries, item is marked as failed."""
    with (
        patch("app.services.worker.fetch_content", new_callable=AsyncMock) as mock_fetch,
        patch("app.services.worker.summarize_content", new_callable=AsyncMock) as mock_summarize,
        patch("app.services.worker.generate_embedding", new_callable=AsyncMock) as mock_embed,
    ):
        mock_fetch.return_value = "Some content"
        mock_summarize.return_value = ("A summary.", ["tag"])
        mock_embed.return_value = None  # Embedding failed

        await enrich_item(pending_item.id, TEST_DATABASE_URL)

    async with TestSession() as session:
        result = await session.execute(select(Item).where(Item.id == pending_item.id))
        item = result.scalar_one()
        assert item.status == ItemStatus.failed


@pytest.mark.asyncio
async def test_enrich_item_sets_status_to_enriching_during_processing(pending_item):
    """Verify item transitions to 'enriching' before processing begins."""
    status_during_fetch = None

    async def capture_status_fetch(url):
        nonlocal status_during_fetch
        async with TestSession() as session:
            result = await session.execute(select(Item).where(Item.id == pending_item.id))
            item = result.scalar_one()
            status_during_fetch = item.status
        return "Content"

    with (
        patch("app.services.worker.fetch_content", side_effect=capture_status_fetch),
        patch("app.services.worker.summarize_content", new_callable=AsyncMock) as mock_summarize,
        patch("app.services.worker.generate_embedding", new_callable=AsyncMock) as mock_embed,
    ):
        mock_summarize.return_value = ("Summary.", ["tag"])
        mock_embed.return_value = [0.1] * 1536

        await enrich_item(pending_item.id, TEST_DATABASE_URL)

    assert status_during_fetch == ItemStatus.enriching
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_worker.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.worker'`

- [ ] **Step 3: Create worker.py**

```python
# backend/app/services/worker.py
"""
Background enrichment worker.

Processes a single item through the full enrichment pipeline:
1. Set status to 'enriching'
2. Fetch page content via trafilatura
3. Summarize with Claude Haiku
4. Generate embedding with OpenAI
5. Update DB and set status to 'enriched' (or 'failed')

Includes retry logic with exponential backoff for API calls.
"""
import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Item, ItemStatus
from app.services.content import fetch_content
from app.services.enrichment import generate_embedding, summarize_content

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2


async def _retry_async(fn, *args, max_retries=MAX_RETRIES):
    """Retry an async function with exponential backoff.

    Returns the function result on success, or None after all retries fail.
    """
    for attempt in range(max_retries):
        result = await fn(*args)
        if result is not None:
            return result
        if attempt < max_retries - 1:
            wait = BASE_BACKOFF_SECONDS * (2 ** attempt)
            logger.info(f"Retry {attempt + 1}/{max_retries} for {fn.__name__}, waiting {wait}s")
            await asyncio.sleep(wait)
    return None


async def enrich_item(item_id: UUID, database_url: str | None = None):
    """Run the full enrichment pipeline for a single item.

    Args:
        item_id: UUID of the item to enrich.
        database_url: Optional database URL override (used in tests).
    """
    from app.config import settings

    db_url = database_url or settings.database_url
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        # Step 1: Set status to enriching
        async with session_factory() as session:
            await session.execute(
                update(Item).where(Item.id == item_id).values(status=ItemStatus.enriching)
            )
            await session.commit()

            result = await session.execute(select(Item).where(Item.id == item_id))
            item = result.scalar_one()
            url = item.url
            title = item.title

        # Step 2: Fetch content
        content = await fetch_content(url)

        # Step 3: Summarize (with retries)
        summarize_result = await _retry_async(summarize_content, title, content)

        if summarize_result is None:
            logger.warning(f"Summarization failed for item {item_id} after {MAX_RETRIES} retries")
            async with session_factory() as session:
                await session.execute(
                    update(Item).where(Item.id == item_id).values(status=ItemStatus.failed)
                )
                await session.commit()
            return

        summary, tags = summarize_result

        # Add content_failed tag if content extraction failed
        if content is None and "content_failed" not in tags:
            tags.append("content_failed")

        # Step 4: Generate embedding (with retries)
        embed_text = f"{title} {summary}"
        embedding = await _retry_async(generate_embedding, embed_text)

        if embedding is None:
            logger.warning(f"Embedding failed for item {item_id} after {MAX_RETRIES} retries")
            async with session_factory() as session:
                await session.execute(
                    update(Item).where(Item.id == item_id).values(status=ItemStatus.failed)
                )
                await session.commit()
            return

        # Step 5: Update item with enrichment results
        async with session_factory() as session:
            await session.execute(
                update(Item)
                .where(Item.id == item_id)
                .values(
                    raw_content=content,
                    summary=summary,
                    tags=tags,
                    embedding=embedding,
                    status=ItemStatus.enriched,
                    processed_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        logger.info(f"Successfully enriched item {item_id}")

    except Exception as e:
        logger.error(f"Unexpected error enriching item {item_id}: {e}")
        try:
            async with session_factory() as session:
                await session.execute(
                    update(Item).where(Item.id == item_id).values(status=ItemStatus.failed)
                )
                await session.commit()
        except Exception:
            logger.error(f"Failed to mark item {item_id} as failed")
    finally:
        await engine.dispose()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/test_worker.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/worker.py backend/tests/test_worker.py
git commit -m "feat: add background enrichment worker with retry logic"
```

---

### Task 5: Hook enrichment into POST /api/items

**Files:**
- Modify: `backend/app/routers/items.py`
- Modify: `backend/tests/test_items.py`

- [ ] **Step 1: Write test for enrichment trigger on item creation**

Append to `backend/tests/test_items.py`:

```python
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_create_item_triggers_enrichment(client):
    """Verify that creating a new item triggers the background enrichment worker."""
    with patch("app.routers.items.trigger_enrichment", new_callable=AsyncMock) as mock_trigger:
        response = await client.post(
            "/api/items",
            json={
                "url": "https://example.com/trigger-test",
                "title": "Trigger Test",
                "source": "chrome",
            },
            headers={"X-API-Key": "change-me"},
        )
        assert response.status_code == 201
        item_id = response.json()["id"]
        mock_trigger.assert_called_once_with(item_id)


@pytest.mark.asyncio
async def test_upsert_does_not_trigger_enrichment(client):
    """Verify that upserting an existing item does NOT re-trigger enrichment."""
    headers = {"X-API-Key": "change-me"}

    with patch("app.routers.items.trigger_enrichment", new_callable=AsyncMock) as mock_trigger:
        await client.post(
            "/api/items",
            json={"url": "https://example.com/upsert-test", "title": "First", "source": "chrome"},
            headers=headers,
        )
        mock_trigger.reset_mock()

        await client.post(
            "/api/items",
            json={"url": "https://example.com/upsert-test", "title": "Updated", "source": "chrome"},
            headers=headers,
        )
        mock_trigger.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_items.py::test_create_item_triggers_enrichment -v
```

Expected: FAIL

- [ ] **Step 3: Update routers/items.py to trigger enrichment**

Add the `trigger_enrichment` function and update `create_item` in `backend/app/routers/items.py`:

```python
# Add these imports at the top of backend/app/routers/items.py
import asyncio
import logging

from app.services.worker import enrich_item

logger = logging.getLogger(__name__)


async def trigger_enrichment(item_id: str):
    """Fire-and-forget background task to enrich an item."""
    asyncio.create_task(_run_enrichment(item_id))


async def _run_enrichment(item_id: str):
    """Wrapper to catch and log errors from the enrichment worker."""
    try:
        from uuid import UUID
        await enrich_item(UUID(item_id))
    except Exception as e:
        logger.error(f"Background enrichment failed for {item_id}: {e}")
```

Then update the `create_item` endpoint to call `trigger_enrichment` for new items (not upserts):

```python
@router.post("", response_model=ItemRead)
async def create_item(
    item: ItemCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_api_key),
):
    # Check if URL already exists
    existing = await session.execute(select(Item).where(Item.url == item.url))
    is_update = existing.scalar_one_or_none() is not None

    stmt = (
        insert(Item)
        .values(
            url=item.url,
            title=item.title,
            source=SourceType(item.source),
            raw_content=item.raw_content,
            created_at=item.timestamp if item.timestamp else None,
        )
        .on_conflict_do_update(
            index_elements=["url"],
            set_={"title": item.title, "raw_content": item.raw_content},
        )
        .returning(Item)
    )
    result = await session.execute(stmt)
    await session.commit()
    db_item = result.scalar_one()

    # Trigger enrichment for new items only
    if not is_update:
        await trigger_enrichment(str(db_item.id))

    from fastapi.responses import JSONResponse
    status_code = 200 if is_update else 201
    return JSONResponse(
        content=ItemRead.model_validate(db_item).model_dump(mode="json"),
        status_code=status_code,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/test_items.py -v
```

Expected: All tests pass (including new trigger tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/items.py backend/tests/test_items.py
git commit -m "feat: trigger background enrichment on item ingest"
```

---

### Task 6: Startup sweep for stuck/failed items

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_startup_sweep.py`

- [ ] **Step 1: Write failing tests for the startup sweep**

```python
# backend/tests/test_startup_sweep.py
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base, Item, ItemStatus, SourceType

TEST_DATABASE_URL = settings.database_url.replace("/insight", "/insight_test")
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session():
    async with TestSession() as session:
        yield session


async def _create_item(session, status):
    item = Item(
        id=uuid.uuid4(),
        url=f"https://example.com/{uuid.uuid4()}",
        title="Test",
        source=SourceType.chrome,
        status=status,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@pytest.mark.asyncio
async def test_sweep_requeues_enriching_items(db_session):
    """Items stuck in 'enriching' (from a crash) should be reset to pending and re-queued."""
    from app.services.worker import sweep_stuck_items

    stuck_item = await _create_item(db_session, ItemStatus.enriching)
    enriched_item = await _create_item(db_session, ItemStatus.enriched)

    triggered_ids = []

    async def mock_trigger(item_id, db_url):
        triggered_ids.append(item_id)

    with patch("app.services.worker.enrich_item", side_effect=mock_trigger):
        await sweep_stuck_items(TEST_DATABASE_URL)

    # Verify stuck item was re-queued
    assert stuck_item.id in triggered_ids
    # Verify enriched item was NOT re-queued
    assert enriched_item.id not in triggered_ids


@pytest.mark.asyncio
async def test_sweep_requeues_failed_items(db_session):
    """Items in 'failed' status should be retried on startup."""
    from app.services.worker import sweep_stuck_items

    failed_item = await _create_item(db_session, ItemStatus.failed)

    triggered_ids = []

    async def mock_trigger(item_id, db_url):
        triggered_ids.append(item_id)

    with patch("app.services.worker.enrich_item", side_effect=mock_trigger):
        await sweep_stuck_items(TEST_DATABASE_URL)

    assert failed_item.id in triggered_ids


@pytest.mark.asyncio
async def test_sweep_resets_status_to_pending(db_session):
    """Swept items should be set back to 'pending' before re-enrichment."""
    from app.services.worker import sweep_stuck_items

    stuck_item = await _create_item(db_session, ItemStatus.enriching)

    with patch("app.services.worker.enrich_item", new_callable=AsyncMock):
        await sweep_stuck_items(TEST_DATABASE_URL)

    async with TestSession() as session:
        result = await session.execute(select(Item).where(Item.id == stuck_item.id))
        item = result.scalar_one()
        assert item.status == ItemStatus.pending
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_startup_sweep.py -v
```

Expected: FAIL — `ImportError: cannot import name 'sweep_stuck_items'`

- [ ] **Step 3: Add sweep_stuck_items to worker.py**

Append to `backend/app/services/worker.py`:

```python
async def sweep_stuck_items(database_url: str | None = None):
    """Find items stuck in 'enriching' or 'failed' and re-queue them.

    Called on app startup to recover from crashes or transient failures.
    Resets status to 'pending' and triggers enrichment for each.
    """
    from app.config import settings

    db_url = database_url or settings.database_url
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            result = await session.execute(
                select(Item).where(Item.status.in_([ItemStatus.enriching, ItemStatus.failed]))
            )
            stuck_items = result.scalars().all()

            if not stuck_items:
                logger.info("Startup sweep: no stuck items found")
                return

            logger.info(f"Startup sweep: found {len(stuck_items)} stuck/failed items, re-queuing")

            # Reset all to pending
            for item in stuck_items:
                await session.execute(
                    update(Item).where(Item.id == item.id).values(status=ItemStatus.pending)
                )
            await session.commit()

        # Re-trigger enrichment for each
        for item in stuck_items:
            await enrich_item(item.id, db_url)

    finally:
        await engine.dispose()
```

- [ ] **Step 4: Wire sweep into FastAPI startup event**

Update `backend/app/main.py` to run the sweep on startup:

```python
# backend/app/main.py
import asyncio
import logging

from fastapi import FastAPI

from app.routers.items import router as items_router
from app.routers.digest import router as digest_router
from app.routers.clusters import router as clusters_router

logger = logging.getLogger(__name__)

app = FastAPI(title="Insight", version="0.1.0")

app.include_router(items_router)
app.include_router(digest_router)
app.include_router(clusters_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.on_event("startup")
async def startup_sweep():
    """On startup, sweep for stuck/failed items and re-queue them."""
    from app.services.worker import sweep_stuck_items

    try:
        asyncio.create_task(sweep_stuck_items())
        logger.info("Startup sweep task created")
    except Exception as e:
        logger.error(f"Failed to start sweep task: {e}")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/test_startup_sweep.py -v
```

Expected: 3 passed

- [ ] **Step 6: Run full test suite**

```bash
cd backend
python -m pytest tests/ -v
```

Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/worker.py backend/app/main.py backend/tests/test_startup_sweep.py
git commit -m "feat: add startup sweep for stuck/failed items"
```

---

### Task 7: Upgrade GET /api/items?q= to vector similarity search

**Files:**
- Modify: `backend/app/routers/items.py`
- Modify: `backend/tests/test_items.py`

- [ ] **Step 1: Write failing tests for semantic search**

Append to `backend/tests/test_items.py`:

```python
@pytest.mark.asyncio
async def test_search_items_vector_similarity(client):
    """Test that ?q= uses vector similarity when embeddings exist."""
    headers = {"X-API-Key": "change-me"}

    # Create items with embeddings via direct DB access
    from app.models import Item, ItemStatus, SourceType
    from tests.conftest import get_test_session

    fake_embedding_ai = [0.9] + [0.1] * 1535  # "AI-like" vector
    fake_embedding_cooking = [0.1] + [0.9] * 1535  # "Cooking-like" vector

    async for session in get_test_session():
        import uuid
        ai_item = Item(
            id=uuid.uuid4(),
            url="https://example.com/ai-article",
            title="Understanding Neural Networks",
            source=SourceType.chrome,
            status=ItemStatus.enriched,
            summary="A deep dive into how neural networks learn.",
            embedding=fake_embedding_ai,
        )
        cooking_item = Item(
            id=uuid.uuid4(),
            url="https://example.com/cooking",
            title="Best Pasta Recipes",
            source=SourceType.chrome,
            status=ItemStatus.enriched,
            summary="Traditional Italian pasta recipes for home cooks.",
            embedding=fake_embedding_cooking,
        )
        session.add_all([ai_item, cooking_item])
        await session.commit()

    # Mock the embedding call to return an AI-like query vector
    query_embedding = [0.85] + [0.15] * 1535

    with patch("app.routers.items.generate_embedding", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = query_embedding

        response = await client.get("/api/items?q=artificial+intelligence")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    # The AI article should rank first (closer vector)
    assert data["items"][0]["title"] == "Understanding Neural Networks"


@pytest.mark.asyncio
async def test_search_items_falls_back_to_text_search(client):
    """Test that ?q= falls back to text search if embedding call fails."""
    headers = {"X-API-Key": "change-me"}

    await client.post(
        "/api/items",
        json={"url": "https://example.com/fallback-test", "title": "Quantum Computing Explained", "source": "chrome"},
        headers=headers,
    )

    with patch("app.routers.items.generate_embedding", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = None  # Embedding fails

        response = await client.get("/api/items?q=Quantum")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert "Quantum" in data["items"][0]["title"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_items.py::test_search_items_vector_similarity -v
```

Expected: FAIL

- [ ] **Step 3: Update GET /api/items to support vector search with fallback**

Replace the `list_items` function in `backend/app/routers/items.py`:

```python
# Add this import at the top
from app.services.enrichment import generate_embedding


@router.get("", response_model=ItemList)
async def list_items(
    source: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    # If there's a search query, try vector similarity first
    if q:
        return await _search_items(q, source, limit, offset, session)

    # No search — standard listing
    query = select(Item).order_by(Item.created_at.desc())

    if source:
        query = query.where(Item.source == SourceType(source))

    from sqlalchemy import func as sqlfunc
    count_query = select(sqlfunc.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    query = query.limit(limit).offset(offset)
    result = await session.execute(query)
    items = result.scalars().all()

    return ItemList(items=[ItemRead.model_validate(i) for i in items], total=total)


async def _search_items(
    q: str,
    source: Optional[str],
    limit: int,
    offset: int,
    session: AsyncSession,
) -> ItemList:
    """Search items using vector similarity, falling back to full-text search."""

    # Try to embed the query
    query_embedding = await generate_embedding(q)

    if query_embedding is not None:
        # Vector similarity search using pgvector cosine distance
        query = (
            select(Item)
            .where(Item.embedding.isnot(None))
            .order_by(Item.embedding.cosine_distance(query_embedding))
        )

        if source:
            query = query.where(Item.source == SourceType(source))

        from sqlalchemy import func as sqlfunc
        count_query = select(sqlfunc.count()).select_from(query.subquery())
        total_result = await session.execute(count_query)
        total = total_result.scalar()

        query = query.limit(limit).offset(offset)
        result = await session.execute(query)
        items = result.scalars().all()

        return ItemList(items=[ItemRead.model_validate(i) for i in items], total=total)

    # Fallback: full-text search on title and summary
    query = select(Item).where(
        Item.title.ilike(f"%{q}%") | Item.summary.ilike(f"%{q}%")
    ).order_by(Item.created_at.desc())

    if source:
        query = query.where(Item.source == SourceType(source))

    from sqlalchemy import func as sqlfunc
    count_query = select(sqlfunc.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    query = query.limit(limit).offset(offset)
    result = await session.execute(query)
    items = result.scalars().all()

    return ItemList(items=[ItemRead.model_validate(i) for i in items], total=total)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/test_items.py -v
```

Expected: All tests pass

- [ ] **Step 5: Run full test suite**

```bash
cd backend
python -m pytest tests/ -v
```

Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/items.py backend/tests/test_items.py
git commit -m "feat: upgrade GET /api/items?q= to vector similarity search with text fallback"
```

---

## Phase 3 Completion Checklist

- [ ] `app/services/content.py` extracts article text from HTML using trafilatura
- [ ] `fetch_content(url)` fetches a URL and returns extracted text (or None on failure)
- [ ] `app/services/enrichment.py` generates summaries + tags via Claude Haiku
- [ ] `app/services/enrichment.py` generates 1536-dim embeddings via OpenAI text-embedding-3-small
- [ ] All external API calls (Anthropic, OpenAI, HTTP) are mocked in tests
- [ ] `app/services/worker.py` runs the full enrichment pipeline: fetch → summarize → embed → update DB
- [ ] Item lifecycle managed: pending → enriching → enriched (or failed)
- [ ] Retry logic: 3 retries with exponential backoff on API failures
- [ ] Content extraction failure handled gracefully (title-only enrichment with `content_failed` tag)
- [ ] `POST /api/items` triggers background enrichment for new items (not upserts)
- [ ] Startup sweep re-queues items stuck in `enriching` or `failed` status
- [ ] `GET /api/items?q=` performs vector similarity search (pgvector cosine distance)
- [ ] Vector search falls back to full-text `ILIKE` search if embedding call fails
- [ ] All tests pass
