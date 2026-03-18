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

        raw_text = response.content[0].text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text
            raw_text = raw_text.rsplit("```", 1)[0].strip()
        digest_data = json.loads(raw_text)

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
