import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Cluster, Digest, DigestItem, Item, ItemStatus, SourceType
from app.services.digest import calculate_read_time, run_digest_generation


def _fake_embedding() -> list[float]:
    return np.random.default_rng(42).normal(0, 1, 1536).tolist()


@pytest_asyncio.fixture
async def clustered_items(setup_db):
    """Insert enriched items with cluster assignments, simulating post-clustering state."""
    from tests.conftest import TestSession

    async with TestSession() as session:
        # Create 2 clusters
        cluster_a = Cluster(label="AI & ML", centroid=_fake_embedding(), item_count=3)
        cluster_b = Cluster(label="Web Dev", centroid=_fake_embedding(), item_count=2)
        session.add(cluster_a)
        session.add(cluster_b)
        await session.flush()

        items = []
        for i in range(3):
            item = Item(
                id=uuid.uuid4(),
                url=f"https://example.com/ai/{i}",
                title=f"AI Article {i}",
                source=SourceType.chrome,
                summary=f"This article discusses AI topic {i} in detail with multiple perspectives.",
                tags=["ai", "ml"],
                embedding=_fake_embedding(),
                status=ItemStatus.enriched,
                cluster_id=cluster_a.id,
                created_at=datetime.now(timezone.utc) - timedelta(hours=i),
                processed_at=datetime.now(timezone.utc),
            )
            session.add(item)
            items.append(item)

        for i in range(2):
            item = Item(
                id=uuid.uuid4(),
                url=f"https://example.com/web/{i}",
                title=f"Web Dev Article {i}",
                source=SourceType.youtube,
                summary=f"This video covers web development topic {i} with practical examples.",
                tags=["web", "frontend"],
                embedding=_fake_embedding(),
                status=ItemStatus.enriched,
                cluster_id=cluster_b.id,
                created_at=datetime.now(timezone.utc) - timedelta(hours=i),
                processed_at=datetime.now(timezone.utc),
            )
            session.add(item)
            items.append(item)

        await session.commit()
    return items


def test_calculate_read_time():
    """Read time = total_words / 200 + item_count * 0.25"""
    assert calculate_read_time(total_words=400, item_count=5) == 3
    assert calculate_read_time(total_words=1000, item_count=10) == 8
    assert calculate_read_time(total_words=10, item_count=1) == 1


@pytest.mark.asyncio
async def test_run_digest_generation_creates_digest(clustered_items):
    """Digest generation creates a digest with correct JSONB structure."""
    from tests.conftest import TestSession

    sonnet_response_json = '''{
        "clusters": [
            {
                "label": "AI & ML",
                "insight": "You have been exploring the cutting edge of artificial intelligence and machine learning. The articles span foundational concepts to advanced applications, suggesting a deepening interest in how AI systems are built and deployed."
            },
            {
                "label": "Web Dev",
                "insight": "Your web development saves focus on modern frontend frameworks and patterns. There is a clear thread connecting server-side rendering innovations with component architecture evolution."
            }
        ],
        "connections": [
            {
                "between": ["AI & ML", "Web Dev"],
                "insight": "AI-powered development tools are increasingly intersecting with frontend frameworks, as seen in your saves about both AI agents and React Server Components."
            }
        ]
    }'''

    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text=sonnet_response_json)]

    with patch("app.services.digest.anthropic_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await run_digest_generation(session_factory=TestSession)

    assert result is not None
    assert result["item_count"] == 5

    # Verify digest in DB
    async with TestSession() as session:
        digest = (await session.execute(select(Digest))).scalar_one()
        assert digest.item_count == 5
        assert "clusters" in digest.content
        assert "connections" in digest.content
        assert "meta" in digest.content
        assert digest.content["meta"]["item_count"] == 5
        assert digest.content["meta"]["cluster_count"] == 2
        assert digest.content["meta"]["estimated_read_minutes"] >= 1

        # Verify digest_items join records
        digest_items = (await session.execute(select(DigestItem))).scalars().all()
        assert len(digest_items) == 5


@pytest.mark.asyncio
async def test_run_digest_skips_when_no_new_items(setup_db):
    """Digest generation is skipped when there are no new enriched items."""
    from tests.conftest import TestSession

    result = await run_digest_generation(session_factory=TestSession)
    assert result is None


@pytest.mark.asyncio
async def test_run_digest_excludes_already_digested_items(clustered_items):
    """Items already in a previous digest are not included again."""
    from tests.conftest import TestSession

    sonnet_response_json = '{"clusters": [{"label": "AI & ML", "insight": "Test insight."}, {"label": "Web Dev", "insight": "Test insight."}], "connections": []}'

    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text=sonnet_response_json)]

    with patch("app.services.digest.anthropic_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        # First run — should include all 5 items
        result1 = await run_digest_generation(session_factory=TestSession)
        assert result1["item_count"] == 5

        # Second run — no new items, should skip
        result2 = await run_digest_generation(session_factory=TestSession)
        assert result2 is None
