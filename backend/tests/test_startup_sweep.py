import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base, Item, ItemStatus, SourceType
from app.services.worker import sweep_stuck_items

_base = settings.database_url.rsplit("/", 1)[0]
TEST_DATABASE_URL = f"{_base}/insight_test"


@pytest_asyncio.fixture
async def sweep_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def sweep_session(sweep_engine):
    session_factory = async_sessionmaker(sweep_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
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
async def test_sweep_requeues_enriching_items(sweep_session):
    """Items stuck in 'enriching' (from a crash) should be reset to pending and re-queued."""
    stuck_item = await _create_item(sweep_session, ItemStatus.enriching)
    enriched_item = await _create_item(sweep_session, ItemStatus.enriched)

    triggered_ids = []

    async def mock_trigger(item_id, db_url):
        triggered_ids.append(item_id)

    with patch("app.services.worker.enrich_item", side_effect=mock_trigger):
        await sweep_stuck_items(TEST_DATABASE_URL)

    assert stuck_item.id in triggered_ids
    assert enriched_item.id not in triggered_ids


@pytest.mark.asyncio
async def test_sweep_requeues_failed_items(sweep_session):
    """Items in 'failed' status should be retried on startup."""
    failed_item = await _create_item(sweep_session, ItemStatus.failed)

    triggered_ids = []

    async def mock_trigger(item_id, db_url):
        triggered_ids.append(item_id)

    with patch("app.services.worker.enrich_item", side_effect=mock_trigger):
        await sweep_stuck_items(TEST_DATABASE_URL)

    assert failed_item.id in triggered_ids


@pytest.mark.asyncio
async def test_sweep_resets_status_to_pending(sweep_session, sweep_engine):
    """Swept items should be set back to 'pending' before re-enrichment."""
    stuck_item = await _create_item(sweep_session, ItemStatus.enriching)

    with patch("app.services.worker.enrich_item", new_callable=AsyncMock):
        await sweep_stuck_items(TEST_DATABASE_URL)

    session_factory = async_sessionmaker(sweep_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(select(Item).where(Item.id == stuck_item.id))
        item = result.scalar_one()
        assert item.status == ItemStatus.pending
