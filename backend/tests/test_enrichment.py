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


# --- Embedding tests ---


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
