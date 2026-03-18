from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Cluster
from app.schemas import ClusterRead

router = APIRouter(prefix="/api/clusters", tags=["clusters"])


@router.get("", response_model=list[ClusterRead])
async def list_clusters(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Cluster).order_by(Cluster.item_count.desc()))
    return result.scalars().all()


@router.post("/run")
async def run_clustering_now():
    """Manually trigger clustering (same logic as the 3 AM scheduled job)."""
    from app.services.clustering import run_clustering

    result = await run_clustering()
    if result is None:
        return {"status": "skipped", "message": "Not enough enriched items (minimum 10 with embeddings)."}
    return result
