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
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text
        raw_text = raw_text.rsplit("```", 1)[0].strip()
    labels = json.loads(raw_text)
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
