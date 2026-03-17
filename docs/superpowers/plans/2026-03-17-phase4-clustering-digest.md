# Phase 4: Clustering + Digest Generation

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cluster enriched items by theme nightly and generate a structured AI-written daily digest that synthesizes what the user has been saving.

**Architecture:** Two scheduled jobs run in-process via APScheduler: a 3:00 AM clustering job that rebuilds K-means clusters from the last 30 days of embeddings, and a 7:00 AM digest job that sends clustered items to Claude Sonnet for synthesis. A manual trigger endpoint (`POST /api/digest/generate`) allows on-demand generation. Clusters are ephemeral (rebuilt nightly); digests are immutable once created.

**Tech Stack:** scikit-learn (K-means, silhouette_score), numpy, APScheduler 3.x, Anthropic Claude Haiku (cluster labels), Anthropic Claude Sonnet (digest generation), SQLAlchemy async

**Spec:** `docs/superpowers/specs/2026-03-17-personal-knowledge-digest-design.md`

---

### Task 1: Clustering service

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/clustering.py`
- Create: `backend/tests/test_clustering.py`

- [ ] **Step 1: Create services/__init__.py**

```python
# backend/app/services/__init__.py
```

Empty file, marks it as a package.

- [ ] **Step 2: Write tests for clustering service**

```python
# backend/tests/test_clustering.py
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
    """Test that Haiku is called to generate labels and returns strings."""
    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text='["AI & Machine Learning", "DevOps & Cloud", "Frontend Web Dev"]')]

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
    assert all(isinstance(label, str) for label in labels)


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

    from tests.conftest import get_test_session

    result = await run_clustering(session_factory=TestSession)
    assert result is None


@pytest.mark.asyncio
async def test_run_clustering_creates_clusters(enriched_items):
    """Full clustering run creates clusters and assigns items."""
    from tests.conftest import TestSession

    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text='["AI & ML", "DevOps", "Frontend"]')]

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
    mock_response.content = [AsyncMock(text='["AI & ML", "DevOps", "Frontend"]')]

    with patch("app.services.clustering.anthropic_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        await run_clustering(session_factory=TestSession)
        first_run_clusters = []
        async with TestSession() as session:
            first_run_clusters = (await session.execute(select(Cluster))).scalars().all()
            first_ids = {c.id for c in first_run_clusters}

        # Run again
        mock_response2 = AsyncMock()
        mock_response2.content = [AsyncMock(text='["Cluster A", "Cluster B", "Cluster C"]')]
        mock_client.messages.create = AsyncMock(return_value=mock_response2)
        await run_clustering(session_factory=TestSession)

        async with TestSession() as session:
            new_clusters = (await session.execute(select(Cluster))).scalars().all()
            new_ids = {c.id for c in new_clusters}
            # Old cluster IDs should be gone
            assert first_ids.isdisjoint(new_ids)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_clustering.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.clustering'`

- [ ] **Step 4: Create clustering.py**

```python
# backend/app/services/clustering.py
"""
Nightly clustering service.

Loads embeddings from the last 30 days, runs K-means with silhouette scoring
to pick the best k (3-7), generates labels via Haiku, and replaces all
existing clusters.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

import anthropic
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.database import async_session
from app.models import Cluster, Item, ItemStatus

logger = logging.getLogger(__name__)

anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

MINIMUM_ITEMS = 10
K_MIN = 3
K_MAX = 7
LOOKBACK_DAYS = 30


def find_best_k(embeddings: np.ndarray, k_min: int = K_MIN, k_max: int = K_MAX) -> int:
    """
    Test k values from k_min to k_max using silhouette scoring.
    Returns the k with the highest silhouette score.
    """
    n_samples = embeddings.shape[0]
    # k_max cannot exceed n_samples - 1
    effective_k_max = min(k_max, n_samples - 1)
    if effective_k_max < k_min:
        return k_min

    best_k = k_min
    best_score = -1.0

    for k in range(k_min, effective_k_max + 1):
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(embeddings)
        score = silhouette_score(embeddings, labels)
        logger.info(f"k={k}, silhouette_score={score:.4f}")
        if score > best_score:
            best_score = score
            best_k = k

    logger.info(f"Best k={best_k} with silhouette_score={best_score:.4f}")
    return best_k


async def generate_cluster_labels(cluster_titles: list[list[str]]) -> list[str]:
    """
    Use Haiku to generate a short descriptive label for each cluster
    based on the titles of items in that cluster.
    """
    cluster_descriptions = []
    for i, titles in enumerate(cluster_titles):
        cluster_descriptions.append(f"Cluster {i + 1}: {', '.join(titles[:10])}")

    prompt = (
        "Given these clusters of saved content, generate a short descriptive label "
        "(2-5 words) for each cluster. Return a JSON array of strings, one label per cluster.\n\n"
        + "\n".join(cluster_descriptions)
        + "\n\nReturn ONLY a JSON array of strings, no other text."
    )

    response = await anthropic_client.messages.create(
        model="claude-3-5-haiku-latest",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    labels = json.loads(response.content[0].text)
    return labels


async def run_clustering(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict | None:
    """
    Main clustering pipeline:
    1. Load enriched items from last 30 days
    2. Check minimum threshold (10 items)
    3. Find best k via silhouette scoring
    4. Run K-means
    5. Generate labels via Haiku
    6. Delete old clusters, insert new ones, reassign items

    Returns summary dict or None if skipped.
    """
    factory = session_factory or async_session
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    async with factory() as session:
        # Load enriched items with embeddings from last 30 days
        result = await session.execute(
            select(Item)
            .where(
                Item.status == ItemStatus.enriched,
                Item.embedding.isnot(None),
                Item.created_at >= cutoff,
            )
            .order_by(Item.created_at.desc())
        )
        items = result.scalars().all()

        if len(items) < MINIMUM_ITEMS:
            logger.info(
                f"Only {len(items)} enriched items (minimum {MINIMUM_ITEMS}). Skipping clustering."
            )
            return None

        logger.info(f"Clustering {len(items)} items from the last {LOOKBACK_DAYS} days")

        # Build embedding matrix
        item_ids = [item.id for item in items]
        embeddings = np.array([item.embedding for item in items])

        # Find best k
        best_k = find_best_k(embeddings)

        # Run final K-means with best k
        kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(embeddings)
        centroids = kmeans.cluster_centers_

        # Gather titles per cluster for label generation
        cluster_titles: list[list[str]] = [[] for _ in range(best_k)]
        cluster_item_ids: list[list] = [[] for _ in range(best_k)]
        for idx, label in enumerate(labels):
            cluster_titles[label].append(items[idx].title)
            cluster_item_ids[label].append(item_ids[idx])

        # Generate labels via Haiku
        cluster_labels = await generate_cluster_labels(cluster_titles)

        # Delete all existing clusters (ON DELETE SET NULL clears items.cluster_id)
        await session.execute(delete(Cluster))
        await session.flush()

        # Insert new clusters and assign items
        for i in range(best_k):
            cluster = Cluster(
                label=cluster_labels[i] if i < len(cluster_labels) else f"Cluster {i + 1}",
                centroid=centroids[i].tolist(),
                item_count=len(cluster_item_ids[i]),
            )
            session.add(cluster)
            await session.flush()  # Get the cluster.id

            # Assign items to this cluster
            if cluster_item_ids[i]:
                await session.execute(
                    update(Item)
                    .where(Item.id.in_(cluster_item_ids[i]))
                    .values(cluster_id=cluster.id)
                )

        await session.commit()

        logger.info(f"Clustering complete: {best_k} clusters, {len(items)} items")
        return {
            "cluster_count": best_k,
            "item_count": len(items),
            "labels": cluster_labels[:best_k],
        }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/test_clustering.py -v
```

Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ backend/tests/test_clustering.py
git commit -m "feat: add clustering service with K-means, silhouette scoring, and Haiku labels"
```

---

### Task 2: Digest generation service

**Files:**
- Create: `backend/app/services/digest.py`
- Create: `backend/tests/test_digest_generation.py`

- [ ] **Step 1: Write tests for digest generation service**

```python
# backend/tests/test_digest_generation.py
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
    # 400 words across insights, 5 items => 400/200 + 5*0.25 = 2 + 1.25 = 3.25 => 3
    assert calculate_read_time(total_words=400, item_count=5) == 3
    # 1000 words, 10 items => 1000/200 + 10*0.25 = 5 + 2.5 = 7.5 => 8
    assert calculate_read_time(total_words=1000, item_count=10) == 8
    # Minimum 1 minute
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_digest_generation.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.digest'`

- [ ] **Step 3: Create digest.py**

```python
# backend/app/services/digest.py
"""
Daily digest generation service.

Collects enriched items not yet included in any digest, groups them by cluster,
sends them to Claude Sonnet for synthesis, and stores the result as JSONB.
"""
import json
import logging
import math
from datetime import date, datetime, timezone

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.database import async_session
from app.models import Cluster, Digest, DigestItem, Item, ItemStatus

logger = logging.getLogger(__name__)

anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


def calculate_read_time(total_words: int, item_count: int) -> int:
    """
    Estimated read time in minutes.
    Formula: total_words_in_insights / 200 + item_count * 0.25
    Minimum 1 minute.
    """
    minutes = total_words / 200 + item_count * 0.25
    return max(1, round(minutes))


async def run_digest_generation(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict | None:
    """
    Main digest generation pipeline:
    1. Find enriched items not yet in any digest
    2. Group by cluster
    3. Send to Sonnet for insight generation
    4. Store digest as JSONB
    5. Create digest_items join records

    Returns summary dict or None if skipped.
    """
    factory = session_factory or async_session

    async with factory() as session:
        # Find items that are enriched but not yet in any digest
        subquery = select(DigestItem.item_id)
        result = await session.execute(
            select(Item)
            .where(
                Item.status == ItemStatus.enriched,
                Item.id.notin_(subquery),
            )
            .order_by(Item.created_at.desc())
        )
        new_items = result.scalars().all()

        if not new_items:
            logger.info("No new enriched items since last digest. Skipping.")
            return None

        logger.info(f"Generating digest for {len(new_items)} new items")

        # Group items by cluster
        clustered: dict[int | None, list[Item]] = {}
        for item in new_items:
            key = item.cluster_id
            if key not in clustered:
                clustered[key] = []
            clustered[key].append(item)

        # Load cluster labels
        cluster_labels: dict[int, str] = {}
        if any(k is not None for k in clustered.keys()):
            cluster_ids = [k for k in clustered.keys() if k is not None]
            clusters_result = await session.execute(
                select(Cluster).where(Cluster.id.in_(cluster_ids))
            )
            for cluster in clusters_result.scalars().all():
                cluster_labels[cluster.id] = cluster.label

        # Build prompt for Sonnet
        prompt_sections = []
        for cluster_id, items in clustered.items():
            label = cluster_labels.get(cluster_id, "Uncategorized") if cluster_id else "Uncategorized"
            items_text = []
            for item in items:
                items_text.append(
                    f"- Title: {item.title}\n  URL: {item.url}\n  Source: {item.source.value}\n  Summary: {item.summary or 'No summary'}"
                )
            prompt_sections.append(
                f"## Cluster: {label}\n" + "\n".join(items_text)
            )

        prompt = (
            "You are generating a personal knowledge digest. The user has saved the following "
            "items, grouped by theme cluster. For each cluster, write an insight paragraph "
            "(3-5 sentences) that SYNTHESIZES the items — do not just list them. Identify "
            "patterns, emerging interests, and connections.\n\n"
            "Also identify any cross-cluster connections: themes that bridge two or more clusters.\n\n"
            + "\n\n".join(prompt_sections)
            + "\n\nReturn your response as JSON with this exact structure:\n"
            '{"clusters": [{"label": "cluster name", "insight": "3-5 sentence synthesis"}], '
            '"connections": [{"between": ["Cluster A", "Cluster B"], "insight": "connection description"}]}\n\n'
            "Return ONLY valid JSON, no other text."
        )

        response = await anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        digest_data = json.loads(response.content[0].text)

        # Enrich digest_data with item details per cluster
        enriched_clusters = []
        total_insight_words = 0
        for cluster_entry in digest_data.get("clusters", []):
            label = cluster_entry["label"]
            insight = cluster_entry["insight"]
            total_insight_words += len(insight.split())

            # Find matching cluster_id for this label
            matching_cluster_id = None
            for cid, clabel in cluster_labels.items():
                if clabel == label:
                    matching_cluster_id = cid
                    break

            # Get items for this cluster
            cluster_items_list = clustered.get(matching_cluster_id, [])
            if not cluster_items_list and label == "Uncategorized":
                cluster_items_list = clustered.get(None, [])

            enriched_clusters.append({
                "label": label,
                "insight": insight,
                "items": [
                    {
                        "id": str(item.id),
                        "title": item.title,
                        "url": item.url,
                        "source": item.source.value,
                        "summary": item.summary,
                    }
                    for item in cluster_items_list
                ],
            })

        # Count words in connection insights too
        for conn in digest_data.get("connections", []):
            total_insight_words += len(conn.get("insight", "").split())

        estimated_read_minutes = calculate_read_time(total_insight_words, len(new_items))

        # Build final content JSONB
        content = {
            "clusters": enriched_clusters,
            "connections": digest_data.get("connections", []),
            "meta": {
                "item_count": len(new_items),
                "cluster_count": len(enriched_clusters),
                "estimated_read_minutes": estimated_read_minutes,
            },
        }

        # Create digest record
        today = date.today()
        digest = Digest(
            date=datetime(today.year, today.month, today.day, tzinfo=timezone.utc),
            content=content,
            item_count=len(new_items),
        )
        session.add(digest)
        await session.flush()

        # Create digest_items join records
        for item in new_items:
            session.add(DigestItem(digest_id=digest.id, item_id=item.id))

        await session.commit()

        logger.info(
            f"Digest generated: {len(new_items)} items, "
            f"{len(enriched_clusters)} clusters, "
            f"~{estimated_read_minutes} min read"
        )
        return {
            "digest_id": digest.id,
            "item_count": len(new_items),
            "cluster_count": len(enriched_clusters),
            "estimated_read_minutes": estimated_read_minutes,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/test_digest_generation.py -v
```

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/digest.py backend/tests/test_digest_generation.py
git commit -m "feat: add digest generation service with Sonnet synthesis and JSONB storage"
```

---

### Task 3: APScheduler setup

**Files:**
- Create: `backend/app/scheduler.py`
- Create: `backend/tests/test_scheduler.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write tests for scheduler configuration**

```python
# backend/tests/test_scheduler.py
from unittest.mock import AsyncMock, patch

import pytest

from app.scheduler import configure_scheduler


def test_scheduler_has_two_jobs():
    """Scheduler should register clustering and digest jobs."""
    scheduler = configure_scheduler()
    jobs = scheduler.get_jobs()
    job_ids = {job.id for job in jobs}
    assert "clustering_nightly" in job_ids
    assert "digest_daily" in job_ids


def test_scheduler_clustering_runs_at_3am():
    """Clustering job should be scheduled at 3:00 AM."""
    scheduler = configure_scheduler()
    job = scheduler.get_job("clustering_nightly")
    trigger = job.trigger
    # CronTrigger fields
    assert str(trigger.fields[trigger.FIELD_NAMES.index("hour")]) == "3"
    assert str(trigger.fields[trigger.FIELD_NAMES.index("minute")]) == "0"


def test_scheduler_digest_runs_at_7am():
    """Digest job should be scheduled at 7:00 AM."""
    scheduler = configure_scheduler()
    job = scheduler.get_job("digest_daily")
    trigger = job.trigger
    assert str(trigger.fields[trigger.FIELD_NAMES.index("hour")]) == "7"
    assert str(trigger.fields[trigger.FIELD_NAMES.index("minute")]) == "0"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_scheduler.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.scheduler'`

- [ ] **Step 3: Create scheduler.py**

```python
# backend/app/scheduler.py
"""
APScheduler configuration.

Two cron jobs:
- clustering_nightly: runs at 3:00 AM, rebuilds K-means clusters
- digest_daily: runs at 7:00 AM, generates the daily digest
"""
import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

logger = logging.getLogger(__name__)


async def _run_clustering_job():
    """Wrapper to run clustering in the scheduler context."""
    from app.services.clustering import run_clustering

    logger.info("Scheduler: starting nightly clustering")
    try:
        result = await run_clustering()
        if result:
            logger.info(f"Scheduler: clustering complete — {result}")
        else:
            logger.info("Scheduler: clustering skipped (below threshold)")
    except Exception:
        logger.exception("Scheduler: clustering failed")


async def _run_digest_job():
    """Wrapper to run digest generation in the scheduler context."""
    from app.services.digest import run_digest_generation

    logger.info("Scheduler: starting daily digest generation")
    try:
        result = await run_digest_generation()
        if result:
            logger.info(f"Scheduler: digest generated — {result}")
        else:
            logger.info("Scheduler: digest skipped (no new items)")
    except Exception:
        logger.exception("Scheduler: digest generation failed")


def configure_scheduler() -> AsyncIOScheduler:
    """
    Create and configure the APScheduler instance with both cron jobs.
    Call scheduler.start() separately (typically in FastAPI lifespan).
    """
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        _run_clustering_job,
        trigger=CronTrigger(hour=settings.clustering_hour, minute=0),
        id="clustering_nightly",
        name="Nightly K-means clustering",
        replace_existing=True,
    )

    scheduler.add_job(
        _run_digest_job,
        trigger=CronTrigger(hour=settings.digest_hour, minute=0),
        id="digest_daily",
        name="Daily digest generation",
        replace_existing=True,
    )

    return scheduler
```

- [ ] **Step 4: Integrate scheduler into FastAPI lifespan in main.py**

Add to `backend/app/main.py`:

```python
# backend/app/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.scheduler import configure_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    scheduler = configure_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    # Shutdown
    scheduler.shutdown()


app = FastAPI(title="Insight", version="0.1.0", lifespan=lifespan)

# ... existing router registrations ...
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/test_scheduler.py -v
```

Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/scheduler.py backend/app/main.py backend/tests/test_scheduler.py
git commit -m "feat: add APScheduler with nightly clustering and daily digest cron jobs"
```

---

### Task 4: POST /api/digest/generate endpoint

**Files:**
- Modify: `backend/app/routers/digest.py`
- Create: `backend/tests/test_digest_endpoint.py`

- [ ] **Step 1: Write tests for manual digest trigger**

```python
# backend/tests/test_digest_endpoint.py
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
import pytest_asyncio

from app.models import Cluster, Item, ItemStatus, SourceType


def _fake_embedding() -> list[float]:
    return np.random.default_rng(42).normal(0, 1, 1536).tolist()


@pytest_asyncio.fixture
async def items_ready_for_digest(setup_db):
    """Insert clustered enriched items ready for digest generation."""
    from tests.conftest import TestSession

    async with TestSession() as session:
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
async def test_manual_digest_trigger(client, items_ready_for_digest):
    """POST /api/digest/generate triggers digest generation and returns result."""
    sonnet_json = '{"clusters": [{"label": "Test Cluster", "insight": "A fascinating collection of test articles."}], "connections": []}'
    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text=sonnet_json)]

    with patch("app.services.digest.anthropic_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        response = await client.post("/api/digest/generate")

    assert response.status_code == 200
    data = response.json()
    assert data["item_count"] == 3
    assert "digest_id" in data


@pytest.mark.asyncio
async def test_manual_digest_trigger_no_items(client, setup_db):
    """POST /api/digest/generate returns 200 with message when no new items."""
    response = await client.post("/api/digest/generate")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "skipped"
    assert "no new items" in data["message"].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_digest_endpoint.py -v
```

Expected: FAIL

- [ ] **Step 3: Add POST /api/digest/generate to digest router**

Update `backend/app/routers/digest.py`:

```python
# backend/app/routers/digest.py
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Digest
from app.schemas import DigestRead

router = APIRouter(prefix="/api/digest", tags=["digest"])


@router.get("/today", response_model=DigestRead)
async def get_today_digest(session: AsyncSession = Depends(get_session)):
    today = date.today()
    result = await session.execute(
        select(Digest).where(
            Digest.date >= datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        )
    )
    digest = result.scalar_one_or_none()
    if not digest:
        raise HTTPException(status_code=404, detail="No digest for today")
    return digest


@router.get("/{digest_date}", response_model=DigestRead)
async def get_digest_by_date(
    digest_date: date, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(Digest).where(
            Digest.date >= datetime(digest_date.year, digest_date.month, digest_date.day, tzinfo=timezone.utc),
            Digest.date
            < datetime(digest_date.year, digest_date.month, digest_date.day + 1, tzinfo=timezone.utc),
        )
    )
    digest = result.scalar_one_or_none()
    if not digest:
        raise HTTPException(status_code=404, detail=f"No digest for {digest_date}")
    return digest


@router.post("/generate")
async def generate_digest():
    """Manually trigger digest generation."""
    from app.services.digest import run_digest_generation

    result = await run_digest_generation()
    if result is None:
        return {"status": "skipped", "message": "No new items to include in digest."}
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/test_digest_endpoint.py -v
```

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/digest.py backend/tests/test_digest_endpoint.py
git commit -m "feat: add POST /api/digest/generate endpoint for manual trigger"
```

---

### Task 5: Integration test — full pipeline

**Files:**
- Create: `backend/tests/test_phase4_integration.py`

- [ ] **Step 1: Write full pipeline integration test**

```python
# backend/tests/test_phase4_integration.py
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

from app.models import Cluster, Digest, DigestItem, Item, ItemStatus, SourceType
from app.services.clustering import run_clustering
from app.services.digest import run_digest_generation


def _make_embedding(seed: int) -> list[float]:
    """Deterministic fake embedding from seed."""
    return np.random.default_rng(seed).normal(0, 1, 1536).tolist()


@pytest_asyncio.fixture
async def seeded_items(setup_db):
    """
    Insert 12 enriched items forming 3 natural clusters.
    Uses deterministic embeddings so clustering is reproducible.
    """
    from tests.conftest import TestSession

    async with TestSession() as session:
        items = []
        # Cluster A: seeds 100-103 (similar embeddings)
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

        # Cluster B: seeds 200-203
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

        # Cluster C: seeds 300-303
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
async def test_full_pipeline_clustering_then_digest(seeded_items, client):
    """
    Full pipeline:
    1. Run clustering → creates 3 clusters, assigns all 12 items
    2. Run digest generation → creates digest with insights
    3. GET /api/digest/today → returns the generated digest
    4. GET /api/clusters → returns cluster list
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

    # --- Step 3: Verify digest via API ---
    response = await client.get("/api/digest/today")
    assert response.status_code == 200
    data = response.json()
    assert data["item_count"] == 12
    assert len(data["content"]["clusters"]) == 3
    assert len(data["content"]["connections"]) == 1
    assert data["content"]["meta"]["item_count"] == 12
    assert data["content"]["meta"]["estimated_read_minutes"] >= 1

    # --- Step 4: Verify clusters via API ---
    response = await client.get("/api/clusters")
    assert response.status_code == 200
    clusters_data = response.json()
    assert len(clusters_data) == 3
    total_cluster_items = sum(c["item_count"] for c in clusters_data)
    assert total_cluster_items == 12


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
```

- [ ] **Step 2: Run the full integration test**

```bash
cd backend
python -m pytest tests/test_phase4_integration.py -v
```

Expected: All tests pass

- [ ] **Step 3: Run the complete test suite**

```bash
cd backend
python -m pytest tests/ -v
```

Expected: All tests pass (including tests from previous phases)

- [ ] **Step 4: Manual smoke test**

Start the server and trigger a manual digest:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

In another terminal (requires items already ingested and enriched from Phases 1-3):

```bash
# Trigger digest generation manually
curl -X POST http://localhost:8000/api/digest/generate

# Check today's digest
curl http://localhost:8000/api/digest/today

# List clusters
curl http://localhost:8000/api/clusters
```

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_phase4_integration.py
git commit -m "test: add Phase 4 integration test — clustering through digest retrieval"
```

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "chore: Phase 4 complete — clustering, digest generation, and scheduler"
git push origin main
```

---

## Phase 4 Completion Checklist

- [ ] `services/clustering.py` runs K-means on embeddings from the last 30 days
- [ ] Silhouette scoring picks best k between 3 and 7
- [ ] Clustering skips when fewer than 10 enriched items exist
- [ ] Haiku generates short labels for each cluster
- [ ] Old clusters are deleted entirely before new ones are inserted (ON DELETE SET NULL)
- [ ] `services/digest.py` collects enriched items not yet in any digest
- [ ] Items are grouped by cluster and sent to Sonnet for synthesis
- [ ] Sonnet generates insight paragraphs per cluster + cross-cluster connections
- [ ] Digest is stored as JSONB matching the spec schema (clusters, connections, meta)
- [ ] Estimated read time is calculated as `total_words / 200 + item_count * 0.25`
- [ ] Digest generation skips when no new items exist
- [ ] APScheduler runs clustering at 3:00 AM and digest at 7:00 AM
- [ ] `POST /api/digest/generate` triggers digest generation on demand
- [ ] All AI calls (Anthropic, OpenAI) are mocked in tests
- [ ] Fake numpy embeddings are used in clustering tests
- [ ] Integration test covers full pipeline: clustering → digest → API retrieval
- [ ] All tests pass
