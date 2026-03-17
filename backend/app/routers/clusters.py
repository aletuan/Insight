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
