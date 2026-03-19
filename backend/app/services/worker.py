"""
Background enrichment worker.

Processes a single item through the full enrichment pipeline:
1. Set status to 'enriching'
2. Fetch page content via trafilatura
3. Summarize with Claude Haiku
4. Generate embedding with OpenAI
5. Update DB and set status to 'enriched' (or 'failed')

Includes retry logic with exponential backoff for API calls.
"""
import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Item, ItemStatus
from app.services.content import fetch_content
from app.services.enrichment import generate_embedding, summarize_content

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2


async def _retry_async(fn, *args, max_retries=MAX_RETRIES):
    """Retry an async function with exponential backoff.

    Returns the function result on success, or None after all retries fail.
    """
    for attempt in range(max_retries):
        result = await fn(*args)
        if result is not None:
            return result
        if attempt < max_retries - 1:
            wait = BASE_BACKOFF_SECONDS * (2 ** attempt)
            logger.info(f"Retry {attempt + 1}/{max_retries} for {fn.__name__}, waiting {wait}s")
            await asyncio.sleep(wait)
    return None


async def enrich_item(item_id: UUID, database_url: str | None = None):
    """Run the full enrichment pipeline for a single item.

    Args:
        item_id: UUID of the item to enrich.
        database_url: Optional database URL override (used in tests).
    """
    from app.config import settings

    db_url = database_url or settings.database_url
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        # Step 1: Set status to enriching
        async with session_factory() as session:
            await session.execute(
                update(Item).where(Item.id == item_id).values(status=ItemStatus.enriching)
            )
            await session.commit()

            result = await session.execute(select(Item).where(Item.id == item_id))
            item = result.scalar_one()
            url = item.url
            title = item.title

        # Step 2: Fetch content
        content = await fetch_content(url)

        # Step 3: Summarize (with retries)
        summarize_result = await _retry_async(summarize_content, title, content)

        if summarize_result is None:
            logger.warning(f"Summarization failed for item {item_id} after {MAX_RETRIES} retries")
            async with session_factory() as session:
                await session.execute(
                    update(Item).where(Item.id == item_id).values(status=ItemStatus.failed)
                )
                await session.commit()
            return

        summary, summary_vi, tags, tags_vi = summarize_result

        # Step 4: Generate embedding (with retries)
        embed_text = f"{title} {summary}"
        embedding = await _retry_async(generate_embedding, embed_text)

        if embedding is None:
            logger.warning(f"Embedding failed for item {item_id} after {MAX_RETRIES} retries")
            async with session_factory() as session:
                await session.execute(
                    update(Item).where(Item.id == item_id).values(status=ItemStatus.failed)
                )
                await session.commit()
            return

        # Step 5: Update item with enrichment results
        async with session_factory() as session:
            await session.execute(
                update(Item)
                .where(Item.id == item_id)
                .values(
                    raw_content=content,
                    summary=summary,
                    summary_vi=summary_vi,
                    tags=tags,
                    tags_vi=tags_vi,
                    embedding=embedding,
                    status=ItemStatus.enriched,
                    processed_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        logger.info(f"Successfully enriched item {item_id}")

    except Exception as e:
        logger.error(f"Unexpected error enriching item {item_id}: {e}")
        try:
            async with session_factory() as session:
                await session.execute(
                    update(Item).where(Item.id == item_id).values(status=ItemStatus.failed)
                )
                await session.commit()
        except Exception:
            logger.error(f"Failed to mark item {item_id} as failed")
    finally:
        await engine.dispose()


async def sweep_stuck_items(database_url: str | None = None):
    """Find items stuck in 'enriching' or 'failed' and re-queue them.

    Called on app startup to recover from crashes or transient failures.
    Resets status to 'pending' and triggers enrichment for each.
    """
    from app.config import settings

    db_url = database_url or settings.database_url
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            result = await session.execute(
                select(Item).where(Item.status.in_([ItemStatus.enriching, ItemStatus.failed]))
            )
            stuck_items = result.scalars().all()

            if not stuck_items:
                logger.info("Startup sweep: no stuck items found")
                return

            logger.info(f"Startup sweep: found {len(stuck_items)} stuck/failed items, re-queuing")

            # Reset all to pending
            for item in stuck_items:
                await session.execute(
                    update(Item).where(Item.id == item.id).values(status=ItemStatus.pending)
                )
            await session.commit()

        # Re-trigger enrichment for each
        for item in stuck_items:
            await enrich_item(item.id, db_url)

    finally:
        await engine.dispose()
