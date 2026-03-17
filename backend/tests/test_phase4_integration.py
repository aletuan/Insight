"""
End-to-end integration test for Phase 4:
  Enriched items → Clustering → Digest Generation → API retrieval

All AI calls (Anthropic, OpenAI) are mocked. Embeddings are fake numpy vectors.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Cluster, Digest, DigestItem, Item, ItemStatus, SourceType
from app.services.clustering import run_clustering
from app.services.digest import run_digest_generation


@pytest_asyncio.fixture
async def seeded_items(setup_db):
    """
    Insert 12 enriched items forming 3 natural clusters.
    Uses deterministic embeddings so clustering is reproducible.
    """
    from tests.conftest import TestSession

    async with TestSession() as session:
        items = []
        # Cluster A: ML-like embeddings
        for i in range(4):
            rng = np.random.default_rng(100 + i)
            emb = np.zeros(1536)
            emb[0] = 5.0 + rng.normal(0, 0.1)
            item = Item(
                id=uuid.uuid4(),
                url=f"https://example.com/int/a{i}",
                title=f"Machine Learning Paper {i}",
                source=SourceType.chrome,
                summary=f"An ML paper about neural network architecture variant {i}.",
                tags=["ml", "ai"],
                embedding=emb.tolist(),
                status=ItemStatus.enriched,
                created_at=datetime.now(timezone.utc) - timedelta(days=i),
                processed_at=datetime.now(timezone.utc),
            )
            session.add(item)
            items.append(item)

        # Cluster B: DevOps-like embeddings
        for i in range(4):
            rng = np.random.default_rng(200 + i)
            emb = np.zeros(1536)
            emb[1] = 5.0 + rng.normal(0, 0.1)
            item = Item(
                id=uuid.uuid4(),
                url=f"https://example.com/int/b{i}",
                title=f"DevOps Guide {i}",
                source=SourceType.youtube,
                summary=f"A comprehensive guide to infrastructure topic {i}.",
                tags=["devops", "infra"],
                embedding=emb.tolist(),
                status=ItemStatus.enriched,
                created_at=datetime.now(timezone.utc) - timedelta(days=i),
                processed_at=datetime.now(timezone.utc),
            )
            session.add(item)
            items.append(item)

        # Cluster C: Frontend-like embeddings
        for i in range(4):
            rng = np.random.default_rng(300 + i)
            emb = np.zeros(1536)
            emb[2] = 5.0 + rng.normal(0, 0.1)
            item = Item(
                id=uuid.uuid4(),
                url=f"https://example.com/int/c{i}",
                title=f"React Performance Tip {i}",
                source=SourceType.chrome,
                summary=f"Practical React optimization technique number {i}.",
                tags=["react", "frontend"],
                embedding=emb.tolist(),
                status=ItemStatus.enriched,
                created_at=datetime.now(timezone.utc) - timedelta(days=i),
                processed_at=datetime.now(timezone.utc),
            )
            session.add(item)
            items.append(item)

        await session.commit()
    return items


@pytest.mark.asyncio
async def test_full_pipeline_clustering_then_digest(seeded_items):
    """
    Full pipeline:
    1. Run clustering → creates 3 clusters, assigns all 12 items
    2. Run digest generation → creates digest with insights
    3. Verify DB state
    """
    from tests.conftest import TestSession

    # --- Step 1: Clustering ---
    haiku_response = AsyncMock()
    haiku_response.content = [
        AsyncMock(text='["AI & Machine Learning", "DevOps & Infrastructure", "Frontend & React"]')
    ]

    with patch("app.services.clustering.anthropic_client") as mock_haiku:
        mock_haiku.messages.create = AsyncMock(return_value=haiku_response)
        cluster_result = await run_clustering(session_factory=TestSession)

    assert cluster_result is not None
    assert cluster_result["cluster_count"] == 3
    assert cluster_result["item_count"] == 12

    # Verify all items have cluster assignments
    async with TestSession() as session:
        assigned = (
            await session.execute(select(Item).where(Item.cluster_id.isnot(None)))
        ).scalars().all()
        assert len(assigned) == 12

        clusters = (await session.execute(select(Cluster))).scalars().all()
        assert len(clusters) == 3

    # --- Step 2: Digest generation ---
    sonnet_response_json = '''{
        "clusters": [
            {
                "label": "AI & Machine Learning",
                "insight": "Your recent saves reveal a deep dive into neural network architectures. You are systematically exploring how different model designs affect performance, suggesting preparation for a hands-on ML project."
            },
            {
                "label": "DevOps & Infrastructure",
                "insight": "The infrastructure content you have saved covers the full deployment lifecycle. There is a clear pattern of building toward a robust CI/CD pipeline with modern cloud-native tooling."
            },
            {
                "label": "Frontend & React",
                "insight": "Your React optimization saves indicate active work on a performance-critical frontend. The techniques span rendering, state management, and bundle optimization."
            }
        ],
        "connections": [
            {
                "between": ["AI & Machine Learning", "DevOps & Infrastructure"],
                "insight": "MLOps is the bridge: deploying ML models requires the infrastructure patterns you have been studying."
            }
        ]
    }'''

    sonnet_response = AsyncMock()
    sonnet_response.content = [AsyncMock(text=sonnet_response_json)]

    with patch("app.services.digest.anthropic_client") as mock_sonnet:
        mock_sonnet.messages.create = AsyncMock(return_value=sonnet_response)
        digest_result = await run_digest_generation(session_factory=TestSession)

    assert digest_result is not None
    assert digest_result["item_count"] == 12
    assert digest_result["cluster_count"] == 3

    # Verify digest in DB
    async with TestSession() as session:
        digest = (await session.execute(select(Digest))).scalar_one()
        assert digest.item_count == 12
        assert len(digest.content["clusters"]) == 3
        assert len(digest.content["connections"]) == 1
        assert digest.content["meta"]["item_count"] == 12
        assert digest.content["meta"]["estimated_read_minutes"] >= 1

        digest_items = (await session.execute(select(DigestItem))).scalars().all()
        assert len(digest_items) == 12


@pytest.mark.asyncio
async def test_pipeline_digest_skips_already_digested(seeded_items):
    """After a digest is generated, running again skips (no new items)."""
    from tests.conftest import TestSession

    # Cluster first
    haiku_response = AsyncMock()
    haiku_response.content = [AsyncMock(text='["A", "B", "C"]')]

    with patch("app.services.clustering.anthropic_client") as mock_haiku:
        mock_haiku.messages.create = AsyncMock(return_value=haiku_response)
        await run_clustering(session_factory=TestSession)

    # Generate first digest
    sonnet_json = '{"clusters": [{"label": "A", "insight": "Test."}, {"label": "B", "insight": "Test."}, {"label": "C", "insight": "Test."}], "connections": []}'
    sonnet_response = AsyncMock()
    sonnet_response.content = [AsyncMock(text=sonnet_json)]

    with patch("app.services.digest.anthropic_client") as mock_sonnet:
        mock_sonnet.messages.create = AsyncMock(return_value=sonnet_response)
        result1 = await run_digest_generation(session_factory=TestSession)
        assert result1 is not None
        assert result1["item_count"] == 12

        # Second run — should skip
        result2 = await run_digest_generation(session_factory=TestSession)
        assert result2 is None
