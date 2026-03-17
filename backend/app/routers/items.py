import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models import Item, SourceType
from app.schemas import ItemCreate, ItemList, ItemRead
from app.services.enrichment import generate_embedding

router = APIRouter(prefix="/api/items", tags=["items"])
logger = logging.getLogger(__name__)


async def trigger_enrichment(item_id: str):
    """Fire-and-forget background task to enrich an item."""
    asyncio.create_task(_run_enrichment(item_id))


async def _run_enrichment(item_id: str):
    """Wrapper to catch and log errors from the enrichment worker."""
    try:
        from uuid import UUID
        from app.services.worker import enrich_item
        await enrich_item(UUID(item_id))
    except Exception as e:
        logger.error(f"Background enrichment failed for {item_id}: {e}")


def verify_api_key(x_api_key: str = Header(default=None)):
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("", response_model=ItemRead)
async def create_item(
    item: ItemCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_api_key),
):
    # Check if URL already exists
    existing = await session.execute(select(Item).where(Item.url == item.url))
    is_update = existing.scalar_one_or_none() is not None

    values = {
        "url": item.url,
        "title": item.title,
        "source": SourceType(item.source),
        "raw_content": item.raw_content,
    }
    if item.timestamp:
        values["created_at"] = item.timestamp

    stmt = (
        insert(Item)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["url"],
            set_={"title": item.title, "raw_content": item.raw_content},
        )
        .returning(Item)
    )
    result = await session.execute(stmt)
    await session.commit()
    db_item = result.scalar_one()

    # Trigger enrichment for new items only
    if not is_update:
        await trigger_enrichment(str(db_item.id))

    status_code = 200 if is_update else 201
    return JSONResponse(
        content=ItemRead.model_validate(db_item).model_dump(mode="json"),
        status_code=status_code,
    )


@router.get("", response_model=ItemList)
async def list_items(
    source: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    # If there's a search query, try vector similarity first
    if q:
        return await _search_items(q, source, limit, offset, session)

    # No search — standard listing
    from sqlalchemy import func as sqlfunc

    query = select(Item).order_by(Item.created_at.desc())

    if source:
        query = query.where(Item.source == SourceType(source))

    count_query = select(sqlfunc.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    query = query.limit(limit).offset(offset)
    result = await session.execute(query)
    items = result.scalars().all()

    return ItemList(items=[ItemRead.model_validate(i) for i in items], total=total)


async def _search_items(
    q: str,
    source: Optional[str],
    limit: int,
    offset: int,
    session: AsyncSession,
) -> ItemList:
    """Search items using vector similarity, falling back to full-text search."""
    from sqlalchemy import func as sqlfunc

    # Try to embed the query
    query_embedding = await generate_embedding(q)

    if query_embedding is not None:
        # Vector similarity search using pgvector cosine distance
        query = (
            select(Item)
            .where(Item.embedding.isnot(None))
            .order_by(Item.embedding.cosine_distance(query_embedding))
        )

        if source:
            query = query.where(Item.source == SourceType(source))

        count_query = select(sqlfunc.count()).select_from(query.subquery())
        total_result = await session.execute(count_query)
        total = total_result.scalar()

        query = query.limit(limit).offset(offset)
        result = await session.execute(query)
        items = result.scalars().all()

        return ItemList(items=[ItemRead.model_validate(i) for i in items], total=total)

    # Fallback: full-text search on title and summary
    query = select(Item).where(
        Item.title.ilike(f"%{q}%") | Item.summary.ilike(f"%{q}%")
    ).order_by(Item.created_at.desc())

    if source:
        query = query.where(Item.source == SourceType(source))

    count_query = select(sqlfunc.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    query = query.limit(limit).offset(offset)
    result = await session.execute(query)
    items = result.scalars().all()

    return ItemList(items=[ItemRead.model_validate(i) for i in items], total=total)
