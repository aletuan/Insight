from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Digest
from app.schemas import DigestRead

router = APIRouter(prefix="/api/digest", tags=["digest"])


def get_digest_session_factory():
    """Return the session factory for digest generation. Override in tests."""
    from app.database import async_session
    return async_session


@router.get("/today", response_model=DigestRead)
async def get_today_digest(session: AsyncSession = Depends(get_session)):
    today = date.today()
    start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    result = await session.execute(
        select(Digest).where(Digest.date >= start).order_by(Digest.date.desc())
    )
    digest = result.scalar_one_or_none()
    if not digest:
        raise HTTPException(status_code=404, detail="No digest for today")
    return digest


@router.get("/{digest_date}", response_model=DigestRead)
async def get_digest_by_date(digest_date: date, session: AsyncSession = Depends(get_session)):
    start = datetime(digest_date.year, digest_date.month, digest_date.day, tzinfo=timezone.utc)
    end = datetime(digest_date.year, digest_date.month, digest_date.day, 23, 59, 59, tzinfo=timezone.utc)
    result = await session.execute(
        select(Digest).where(Digest.date >= start, Digest.date <= end)
    )
    digest = result.scalar_one_or_none()
    if not digest:
        raise HTTPException(status_code=404, detail=f"No digest for {digest_date}")
    return digest


@router.post("/generate")
async def generate_digest(factory=Depends(get_digest_session_factory)):
    """Manually trigger digest generation."""
    from app.services.digest import run_digest_generation

    result = await run_digest_generation(session_factory=factory)
    if result is None:
        return {"status": "skipped", "message": "No new items to include in digest."}
    return result
