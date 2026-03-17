import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class SourceType(str, enum.Enum):
    chrome = "chrome"
    youtube = "youtube"
    x = "x"
    threads = "threads"
    manual = "manual"


class ItemCreate(BaseModel):
    url: str
    title: str
    source: SourceType
    raw_content: Optional[str] = None
    timestamp: Optional[datetime] = None


class ItemRead(BaseModel):
    id: UUID
    url: str
    title: str
    source: SourceType
    status: str
    created_at: datetime
    summary: Optional[str] = None
    tags: Optional[list[str]] = None
    cluster_id: Optional[int] = None
    processed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ItemList(BaseModel):
    items: list[ItemRead]
    total: int


class DigestRead(BaseModel):
    id: int
    date: datetime
    content: dict
    item_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ClusterRead(BaseModel):
    id: int
    label: str
    item_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
