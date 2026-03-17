import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base, Item, ItemStatus, SourceType
from app.services.worker import enrich_item

_base = settings.database_url.rsplit("/", 1)[0]
TEST_DATABASE_URL = f"{_base}/insight_test"


@pytest_asyncio.fixture
async def worker_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def worker_session(worker_engine):
    session_factory = async_sessionmaker(worker_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def pending_item(worker_session):
    item = Item(
        id=uuid.uuid4(),
        url="https://example.com/test-article",
        title="Test Article About AI",
        source=SourceType.chrome,
        status=ItemStatus.pending,
    )
    worker_session.add(item)
    await worker_session.commit()
    await worker_session.refresh(item)
    return item


async def _get_item(item_id):
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(select(Item).where(Item.id == item_id))
        item = result.scalar_one()
    await engine.dispose()
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

    item = await _get_item(pending_item.id)
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
            ["ai"],
        )
        mock_embed.return_value = fake_embedding

        await enrich_item(pending_item.id, TEST_DATABASE_URL)

    item = await _get_item(pending_item.id)
    assert item.status == ItemStatus.enriched


@pytest.mark.asyncio
async def test_enrich_item_summarization_fails_marks_failed(pending_item):
    """If summarization fails after retries, item is marked as failed."""
    with (
        patch("app.services.worker.fetch_content", new_callable=AsyncMock) as mock_fetch,
        patch("app.services.worker.summarize_content", new_callable=AsyncMock) as mock_summarize,
        patch("app.services.worker._retry_async") as mock_retry,
    ):
        mock_fetch.return_value = "Some content"
        mock_retry.return_value = None  # Summarization failed after retries

        await enrich_item(pending_item.id, TEST_DATABASE_URL)

    item = await _get_item(pending_item.id)
    assert item.status == ItemStatus.failed


@pytest.mark.asyncio
async def test_enrich_item_embedding_fails_marks_failed(pending_item):
    """If embedding fails after retries, item is marked as failed."""
    with (
        patch("app.services.worker.fetch_content", new_callable=AsyncMock) as mock_fetch,
        patch("app.services.worker.summarize_content", new_callable=AsyncMock) as mock_summarize,
        patch("app.services.worker.generate_embedding", new_callable=AsyncMock) as mock_embed,
        patch("app.services.worker._retry_async") as mock_retry,
    ):
        mock_fetch.return_value = "Some content"
        # First call to _retry_async (summarize) succeeds, second (embed) fails
        mock_retry.side_effect = [
            ("A summary.", ["tag"]),
            None,
        ]

        await enrich_item(pending_item.id, TEST_DATABASE_URL)

    item = await _get_item(pending_item.id)
    assert item.status == ItemStatus.failed


@pytest.mark.asyncio
async def test_enrich_item_sets_status_to_enriching_during_processing(pending_item, worker_engine):
    """Verify item transitions to 'enriching' before processing begins."""
    status_during_fetch = None
    session_factory = async_sessionmaker(worker_engine, class_=AsyncSession, expire_on_commit=False)

    async def capture_status_fetch(url):
        nonlocal status_during_fetch
        async with session_factory() as session:
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
