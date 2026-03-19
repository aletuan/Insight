import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Cluster, Item, ItemStatus, SourceType
from app.services.clustering import (
    find_best_k,
    generate_cluster_labels,
    run_clustering,
)


def _make_fake_embedding(cluster_center: list[float], noise: float = 0.05) -> list[float]:
    """Create a 1536-dim embedding near a cluster center."""
    rng = np.random.default_rng()
    base = np.zeros(1536)
    for i, v in enumerate(cluster_center):
        base[i] = v
    return (base + rng.normal(0, noise, 1536)).tolist()


def _cluster_a_center():
    return [1.0, 0.0, 0.0]


def _cluster_b_center():
    return [0.0, 1.0, 0.0]


def _cluster_c_center():
    return [0.0, 0.0, 1.0]


@pytest_asyncio.fixture
async def enriched_items(setup_db):
    """Insert 15 enriched items across 3 natural clusters."""
    from tests.conftest import TestSession

    items = []
    centers = [_cluster_a_center(), _cluster_b_center(), _cluster_c_center()]
    titles_per_cluster = [
        ["AI Agents Overview", "LLM Fine-tuning Guide", "Transformer Architecture", "GPT-5 Analysis", "Neural Network Basics"],
        ["Kubernetes Best Practices", "Docker Networking", "CI/CD Pipelines", "Terraform Modules", "AWS Lambda Patterns"],
        ["React Server Components", "Next.js 15 Features", "TypeScript 6.0", "CSS Container Queries", "Web Components Guide"],
    ]

    async with TestSession() as session:
        for cluster_idx, center in enumerate(centers):
            for i in range(5):
                item = Item(
                    id=uuid.uuid4(),
                    url=f"https://example.com/c{cluster_idx}/item{i}",
                    title=titles_per_cluster[cluster_idx][i],
                    source=SourceType.chrome,
                    summary=f"Summary for {titles_per_cluster[cluster_idx][i]}",
                    tags=["test"],
                    embedding=_make_fake_embedding(center),
                    status=ItemStatus.enriched,
                    created_at=datetime.now(timezone.utc) - timedelta(days=i),
                    processed_at=datetime.now(timezone.utc),
                )
                session.add(item)
                items.append(item)
        await session.commit()
    return items


def test_find_best_k_returns_valid_k():
    """Test silhouette scoring picks a reasonable k."""
    rng = np.random.default_rng(42)
    # Create 3 well-separated clusters in 1536 dims
    embeddings = np.zeros((30, 1536))
    for i in range(10):
        embeddings[i, 0] = 5.0 + rng.normal(0, 0.1)
    for i in range(10, 20):
        embeddings[i, 1] = 5.0 + rng.normal(0, 0.1)
    for i in range(20, 30):
        embeddings[i, 2] = 5.0 + rng.normal(0, 0.1)

    best_k = find_best_k(embeddings, k_min=3, k_max=7)
    assert 3 <= best_k <= 7


def test_find_best_k_min_with_few_items():
    """With exactly 10 items, k_max is clamped."""
    rng = np.random.default_rng(42)
    embeddings = rng.normal(0, 1, (10, 1536))
    best_k = find_best_k(embeddings, k_min=3, k_max=7)
    assert 3 <= best_k <= 7


@pytest.mark.asyncio
async def test_generate_cluster_labels():
    """Test that Haiku is called to generate bilingual labels."""
    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text='[{"en": "AI & Machine Learning", "vi": "AI & Học máy"}, {"en": "DevOps & Cloud", "vi": "DevOps & Đám mây"}, {"en": "Frontend Web Dev", "vi": "Phát triển Web Frontend"}]')]

    with patch("app.services.clustering.anthropic_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        labels = await generate_cluster_labels(
            cluster_titles=[
                ["AI Agents Overview", "LLM Guide", "GPT-5"],
                ["Kubernetes", "Docker", "CI/CD"],
                ["React", "Next.js", "TypeScript"],
            ]
        )
    assert len(labels) == 3
    assert all(isinstance(label, dict) for label in labels)
    assert all("en" in label and "vi" in label for label in labels)


@pytest.mark.asyncio
async def test_run_clustering_skips_below_threshold(setup_db):
    """Clustering is skipped when fewer than 10 enriched items exist."""
    from tests.conftest import TestSession

    async with TestSession() as session:
        # Insert only 5 items
        for i in range(5):
            item = Item(
                id=uuid.uuid4(),
                url=f"https://example.com/skip{i}",
                title=f"Item {i}",
                source=SourceType.chrome,
                embedding=_make_fake_embedding([1.0, 0.0, 0.0]),
                status=ItemStatus.enriched,
                created_at=datetime.now(timezone.utc),
                processed_at=datetime.now(timezone.utc),
            )
            session.add(item)
        await session.commit()

    result = await run_clustering(session_factory=TestSession)
    assert result is None


@pytest.mark.asyncio
async def test_run_clustering_creates_clusters(enriched_items):
    """Full clustering run creates clusters and assigns items."""
    from tests.conftest import TestSession

    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text='[{"en": "AI & ML", "vi": "AI & Học máy"}, {"en": "DevOps", "vi": "DevOps"}, {"en": "Frontend", "vi": "Frontend"}]')]

    with patch("app.services.clustering.anthropic_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await run_clustering(session_factory=TestSession)

    assert result is not None
    assert result["cluster_count"] >= 3
    assert result["item_count"] == 15

    # Verify clusters exist in DB
    async with TestSession() as session:
        clusters = (await session.execute(select(Cluster))).scalars().all()
        assert len(clusters) >= 3
        total_items = sum(c.item_count for c in clusters)
        assert total_items == 15

        # Verify items have cluster_id assigned
        items = (await session.execute(
            select(Item).where(Item.cluster_id.isnot(None))
        )).scalars().all()
        assert len(items) == 15


@pytest.mark.asyncio
async def test_run_clustering_replaces_previous_clusters(enriched_items):
    """Running clustering twice replaces old clusters entirely."""
    from tests.conftest import TestSession

    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text='[{"en": "AI & ML", "vi": "AI & Học máy"}, {"en": "DevOps", "vi": "DevOps"}, {"en": "Frontend", "vi": "Frontend"}]')]

    with patch("app.services.clustering.anthropic_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        await run_clustering(session_factory=TestSession)
        async with TestSession() as session:
            first_run_clusters = (await session.execute(select(Cluster))).scalars().all()
            first_ids = {c.id for c in first_run_clusters}

        # Run again
        mock_response2 = AsyncMock()
        mock_response2.content = [AsyncMock(text='[{"en": "Cluster A", "vi": "Cụm A"}, {"en": "Cluster B", "vi": "Cụm B"}, {"en": "Cluster C", "vi": "Cụm C"}]')]
        mock_client.messages.create = AsyncMock(return_value=mock_response2)
        await run_clustering(session_factory=TestSession)

        async with TestSession() as session:
            new_clusters = (await session.execute(select(Cluster))).scalars().all()
            new_ids = {c.id for c in new_clusters}
            # Old cluster IDs should be gone
            assert first_ids.isdisjoint(new_ids)
