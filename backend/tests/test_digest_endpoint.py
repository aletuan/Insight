import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Cluster, Item, ItemStatus, SourceType
from app.routers.digest import get_digest_session_factory


def _fake_embedding() -> list[float]:
    return np.random.default_rng(42).normal(0, 1, 1536).tolist()


@pytest_asyncio.fixture
async def digest_client(db_engine):
    """Client with both get_session and get_digest_session_factory overridden."""
    from typing import AsyncGenerator
    from httpx import ASGITransport, AsyncClient
    from app.database import get_session
    from app.main import app

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def get_test_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    def get_test_factory():
        return session_factory

    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[get_digest_session_factory] = get_test_factory
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def items_ready_for_digest(db_engine):
    """Insert clustered enriched items ready for digest generation."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        cluster = Cluster(label="Test Cluster", centroid=_fake_embedding(), item_count=3)
        session.add(cluster)
        await session.flush()

        for i in range(3):
            item = Item(
                id=uuid.uuid4(),
                url=f"https://example.com/digest-test/{i}",
                title=f"Digest Test Article {i}",
                source=SourceType.chrome,
                summary=f"Summary about topic {i} with detailed analysis.",
                tags=["test"],
                embedding=_fake_embedding(),
                status=ItemStatus.enriched,
                cluster_id=cluster.id,
                created_at=datetime.now(timezone.utc) - timedelta(hours=i),
                processed_at=datetime.now(timezone.utc),
            )
            session.add(item)
        await session.commit()


@pytest.mark.asyncio
async def test_manual_digest_trigger(digest_client, items_ready_for_digest):
    """POST /api/digest/generate triggers digest generation and returns result."""
    sonnet_json = '{"clusters": [{"label": "Test Cluster", "insight": "A fascinating collection of test articles."}], "connections": []}'
    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text=sonnet_json)]

    with patch("app.services.digest.anthropic_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        response = await digest_client.post("/api/digest/generate")

    assert response.status_code == 200
    data = response.json()
    assert data["item_count"] == 3
    assert "digest_id" in data


@pytest.mark.asyncio
async def test_manual_digest_trigger_no_items(digest_client):
    """POST /api/digest/generate returns 200 with message when no new items."""
    response = await digest_client.post("/api/digest/generate")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "skipped"
    assert "no new items" in data["message"].lower()
