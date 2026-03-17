import enum
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class SourceType(str, enum.Enum):
    chrome = "chrome"
    youtube = "youtube"
    x = "x"
    threads = "threads"
    manual = "manual"


class ItemStatus(str, enum.Enum):
    pending = "pending"
    enriching = "enriching"
    enriched = "enriched"
    failed = "failed"


class Item(Base):
    __tablename__ = "items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(Text, nullable=False, unique=True)
    title = Column(Text, nullable=False)
    source = Column(Enum(SourceType), nullable=False)
    raw_content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    tags = Column(ARRAY(String), nullable=True)
    embedding = Column(Vector(1536), nullable=True)
    status = Column(Enum(ItemStatus), nullable=False, default=ItemStatus.pending)
    cluster_id = Column(Integer, ForeignKey("clusters.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)

    cluster = relationship("Cluster", back_populates="items")


class Cluster(Base):
    __tablename__ = "clusters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(Text, nullable=False)
    centroid = Column(Vector(1536), nullable=True)
    item_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    items = relationship("Item", back_populates="cluster")


class Digest(Base):
    __tablename__ = "digests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime(timezone=True), nullable=False, unique=True)
    content = Column(JSONB, nullable=False)
    item_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    digest_items = relationship("DigestItem", back_populates="digest")


class DigestItem(Base):
    __tablename__ = "digest_items"

    digest_id = Column(Integer, ForeignKey("digests.id"), primary_key=True)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id"), primary_key=True)

    digest = relationship("Digest", back_populates="digest_items")
    item = relationship("Item")
