# Phase 1: Ingest API + Postgres Schema + Bookmark Importer

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the data foundation — Postgres schema, FastAPI ingest/read API, and Chrome bookmark HTML importer.

**Architecture:** FastAPI monolith with SQLAlchemy ORM, Alembic migrations, Postgres + pgvector. Single `POST /api/items` endpoint for all capture sources, `GET /api/items` for listing. Bookmark importer is a standalone CLI script that calls the same DB layer.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, SQLAlchemy 2.0, Alembic, asyncpg, pgvector, Pydantic v2, pytest, httpx (test client)

**Spec:** `docs/superpowers/specs/2026-03-17-personal-knowledge-digest-design.md`

---

### Task 1: Project scaffolding and dependencies

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/.env.example`

- [ ] **Step 1: Create backend directory and requirements.txt**

```txt
# backend/requirements.txt
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.1
pgvector==0.3.6
pydantic==2.10.4
pydantic-settings==2.7.1
python-dotenv==1.0.1
httpx==0.28.1
pytest==8.3.4
pytest-asyncio==0.25.0
trafilatura==2.0.0
anthropic==0.43.0
openai==1.59.0
scikit-learn==1.6.1
numpy==2.2.1
apscheduler==3.10.4
```

- [ ] **Step 2: Create .env.example**

```env
# backend/.env.example
DATABASE_URL=postgresql+asyncpg://insight:insight@localhost:5432/insight
API_KEY=change-me-to-a-random-string
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
```

- [ ] **Step 3: Create config.py**

```python
# backend/app/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://insight:insight@localhost:5432/insight"
    api_key: str = "change-me"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    clustering_hour: int = 3
    digest_hour: int = 7

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 4: Create __init__.py**

```python
# backend/app/__init__.py
```

Empty file, just marks it as a package.

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: scaffold backend project with dependencies and config"
```

---

### Task 2: Database connection and SQLAlchemy models

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/models.py`

- [ ] **Step 1: Create database.py**

```python
# backend/app/database.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
```

- [ ] **Step 2: Create models.py with all four tables**

```python
# backend/app/models.py
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
    UniqueConstraint,
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
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/database.py backend/app/models.py
git commit -m "feat: add SQLAlchemy models for items, clusters, digests"
```

---

### Task 3: Alembic setup and initial migration

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/` (auto-generated)

- [ ] **Step 1: Install dependencies and init Alembic**

```bash
cd backend
pip install -r requirements.txt
alembic init alembic
```

- [ ] **Step 2: Edit alembic/env.py to use async engine and import models**

Replace the generated `alembic/env.py` with:

```python
# backend/alembic/env.py
import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.models import Base

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=settings.database_url, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    connectable = create_async_engine(settings.database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 3: Update alembic.ini sqlalchemy.url line**

In `backend/alembic.ini`, set:
```ini
sqlalchemy.url = postgresql+asyncpg://insight:insight@localhost:5432/insight
```

Note: The env.py overrides this with the settings value, but the ini file needs a valid placeholder.

- [ ] **Step 4: Create the Postgres database and enable pgvector**

```bash
createdb insight
psql insight -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

If the `insight` user doesn't exist:
```bash
psql postgres -c "CREATE USER insight WITH PASSWORD 'insight';"
psql postgres -c "GRANT ALL PRIVILEGES ON DATABASE insight TO insight;"
psql insight -c "GRANT ALL ON SCHEMA public TO insight;"
```

- [ ] **Step 5: Generate and run the initial migration**

```bash
cd backend
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

- [ ] **Step 6: Verify tables exist**

```bash
psql insight -c "\dt"
```

Expected: `items`, `clusters`, `digests`, `digest_items`, `alembic_version` tables listed.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/ backend/alembic.ini
git commit -m "feat: add Alembic migrations with initial schema"
```

---

### Task 4: Pydantic schemas for request/response validation

**Files:**
- Create: `backend/app/schemas.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_schemas.py`

- [ ] **Step 1: Write tests for schemas**

```python
# backend/tests/test_schemas.py
from datetime import datetime, timezone

from app.schemas import ItemCreate, ItemRead, SourceType


def test_item_create_valid():
    item = ItemCreate(
        url="https://example.com/article",
        title="Test Article",
        source=SourceType.chrome,
    )
    assert item.url == "https://example.com/article"
    assert item.source == SourceType.chrome


def test_item_create_with_timestamp():
    ts = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    item = ItemCreate(
        url="https://example.com",
        title="Test",
        source=SourceType.youtube,
        timestamp=ts,
    )
    assert item.timestamp == ts


def test_item_read_has_all_fields():
    item = ItemRead(
        id="550e8400-e29b-41d4-a716-446655440000",
        url="https://example.com",
        title="Test",
        source=SourceType.chrome,
        status="pending",
        created_at=datetime.now(timezone.utc),
        summary=None,
        tags=None,
        cluster_id=None,
        processed_at=None,
    )
    assert item.status == "pending"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_schemas.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas'`

- [ ] **Step 3: Create schemas.py**

```python
# backend/app/schemas.py
import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, HttpUrl


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
```

- [ ] **Step 4: Create tests/__init__.py**

```python
# backend/tests/__init__.py
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/test_schemas.py -v
```

Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/tests/
git commit -m "feat: add Pydantic schemas for items, digests, clusters"
```

---

### Task 5: FastAPI app skeleton with health check

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/tests/test_main.py`

- [ ] **Step 1: Write test for health check**

```python
# backend/tests/test_main.py
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
python -m pytest tests/test_main.py -v
```

Expected: FAIL

- [ ] **Step 3: Create main.py**

```python
# backend/app/main.py
from fastapi import FastAPI

app = FastAPI(title="Insight", version="0.1.0")


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend
python -m pytest tests/test_main.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_main.py
git commit -m "feat: add FastAPI app skeleton with health check"
```

---

### Task 6: Items router — POST /api/items

**Files:**
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/items.py`
- Create: `backend/tests/test_items.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Create conftest.py with test database fixtures**

```python
# backend/tests/conftest.py
import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import get_session
from app.main import app
from app.models import Base

# Use a separate test database
TEST_DATABASE_URL = settings.database_url.replace("/insight", "/insight_test")

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def get_test_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    app.dependency_overrides[get_session] = get_test_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

Note: requires creating the `insight_test` database:
```bash
createdb insight_test
psql insight_test -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

- [ ] **Step 2: Write tests for POST /api/items**

```python
# backend/tests/test_items.py
import pytest


@pytest.mark.asyncio
async def test_create_item(client):
    response = await client.post(
        "/api/items",
        json={
            "url": "https://example.com/article",
            "title": "Test Article",
            "source": "chrome",
        },
        headers={"X-API-Key": "change-me"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["url"] == "https://example.com/article"
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_create_item_missing_api_key(client):
    response = await client.post(
        "/api/items",
        json={"url": "https://example.com", "title": "Test", "source": "chrome"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_item_wrong_api_key(client):
    response = await client.post(
        "/api/items",
        json={"url": "https://example.com", "title": "Test", "source": "chrome"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_item_duplicate_url_upserts(client):
    headers = {"X-API-Key": "change-me"}
    await client.post(
        "/api/items",
        json={"url": "https://example.com/dup", "title": "First", "source": "chrome"},
        headers=headers,
    )
    response = await client.post(
        "/api/items",
        json={"url": "https://example.com/dup", "title": "Updated", "source": "chrome"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_items.py -v
```

Expected: FAIL

- [ ] **Step 4: Create routers/__init__.py and routers/items.py**

```python
# backend/app/routers/__init__.py
```

```python
# backend/app/routers/items.py
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models import Item, SourceType
from app.schemas import ItemCreate, ItemRead

router = APIRouter(prefix="/api/items", tags=["items"])


def verify_api_key(x_api_key: str = Header(default=None)):
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("", status_code=201, response_model=ItemRead)
async def create_item(
    item: ItemCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_api_key),
):
    stmt = (
        insert(Item)
        .values(
            url=item.url,
            title=item.title,
            source=SourceType(item.source),
            raw_content=item.raw_content,
            created_at=item.timestamp if item.timestamp else None,
        )
        .on_conflict_do_update(
            index_elements=["url"],
            set_={"title": item.title, "raw_content": item.raw_content},
        )
        .returning(Item)
    )
    result = await session.execute(stmt)
    await session.commit()
    db_item = result.scalar_one()

    # Check if this was an update (already existed) — return 200 instead of 201
    # We can detect this by checking if processed_at is set or status is not pending
    # For simplicity, the upsert always returns the item

    return db_item
```

Note: The 201 vs 200 distinction for upserts requires a small adjustment. Update the route:

```python
@router.post("", response_model=ItemRead)
async def create_item(
    item: ItemCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_api_key),
):
    # Check if URL already exists
    existing = await session.execute(select(Item).where(Item.url == item.url))
    is_update = existing.scalar_one_or_none() is not None

    stmt = (
        insert(Item)
        .values(
            url=item.url,
            title=item.title,
            source=SourceType(item.source),
            raw_content=item.raw_content,
            created_at=item.timestamp if item.timestamp else None,
        )
        .on_conflict_do_update(
            index_elements=["url"],
            set_={"title": item.title, "raw_content": item.raw_content},
        )
        .returning(Item)
    )
    result = await session.execute(stmt)
    await session.commit()
    db_item = result.scalar_one()

    from fastapi.responses import JSONResponse
    status_code = 200 if is_update else 201
    return JSONResponse(
        content=ItemRead.model_validate(db_item).model_dump(mode="json"),
        status_code=status_code,
    )
```

- [ ] **Step 5: Register router in main.py**

Add to `backend/app/main.py`:

```python
from app.routers.items import router as items_router

app.include_router(items_router)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/test_items.py -v
```

Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/ backend/tests/ backend/app/main.py
git commit -m "feat: add POST /api/items endpoint with API key auth and upsert"
```

---

### Task 7: Items router — GET /api/items

**Files:**
- Modify: `backend/app/routers/items.py`
- Modify: `backend/tests/test_items.py`

- [ ] **Step 1: Write tests for GET /api/items**

Append to `backend/tests/test_items.py`:

```python
@pytest.mark.asyncio
async def test_list_items_empty(client):
    response = await client.get("/api/items")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_items_returns_created(client):
    headers = {"X-API-Key": "change-me"}
    await client.post(
        "/api/items",
        json={"url": "https://example.com/1", "title": "First", "source": "chrome"},
        headers=headers,
    )
    await client.post(
        "/api/items",
        json={"url": "https://example.com/2", "title": "Second", "source": "youtube"},
        headers=headers,
    )
    response = await client.get("/api/items")
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_list_items_filter_by_source(client):
    headers = {"X-API-Key": "change-me"}
    await client.post(
        "/api/items",
        json={"url": "https://example.com/c", "title": "Chrome", "source": "chrome"},
        headers=headers,
    )
    await client.post(
        "/api/items",
        json={"url": "https://example.com/y", "title": "YouTube", "source": "youtube"},
        headers=headers,
    )
    response = await client.get("/api/items?source=chrome")
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["source"] == "chrome"
```

- [ ] **Step 2: Run tests to verify new ones fail**

```bash
cd backend
python -m pytest tests/test_items.py::test_list_items_empty -v
```

Expected: FAIL

- [ ] **Step 3: Add GET endpoint to routers/items.py**

```python
from typing import Optional

from app.schemas import ItemList


@router.get("", response_model=ItemList)
async def list_items(
    source: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    query = select(Item).order_by(Item.created_at.desc())

    if source:
        query = query.where(Item.source == SourceType(source))

    # Semantic search (q=) will be implemented in Phase 3 after embeddings exist
    # For now, fall back to text search
    if q:
        query = query.where(
            Item.title.ilike(f"%{q}%") | Item.summary.ilike(f"%{q}%")
        )

    # Count total before pagination
    from sqlalchemy import func as sqlfunc
    count_query = select(sqlfunc.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    query = query.limit(limit).offset(offset)
    result = await session.execute(query)
    items = result.scalars().all()

    return ItemList(items=[ItemRead.model_validate(i) for i in items], total=total)
```

- [ ] **Step 4: Run all tests**

```bash
cd backend
python -m pytest tests/test_items.py -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/items.py backend/tests/test_items.py
git commit -m "feat: add GET /api/items with source filtering and text search"
```

---

### Task 8: Digest and clusters routers (read-only stubs)

**Files:**
- Create: `backend/app/routers/digest.py`
- Create: `backend/app/routers/clusters.py`
- Create: `backend/tests/test_digest.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write tests for digest endpoints**

```python
# backend/tests/test_digest.py
import pytest


@pytest.mark.asyncio
async def test_get_today_digest_empty(client):
    response = await client.get("/api/digest/today")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_digest_by_date_empty(client):
    response = await client.get("/api/digest/2026-03-17")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_clusters_empty(client):
    response = await client.get("/api/clusters")
    assert response.status_code == 200
    assert response.json() == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_digest.py -v
```

Expected: FAIL

- [ ] **Step 3: Create digest router**

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
        select(Digest).where(Digest.date >= datetime(today.year, today.month, today.day, tzinfo=timezone.utc))
    )
    digest = result.scalar_one_or_none()
    if not digest:
        raise HTTPException(status_code=404, detail="No digest for today")
    return digest


@router.get("/{digest_date}", response_model=DigestRead)
async def get_digest_by_date(digest_date: date, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Digest).where(
            Digest.date >= datetime(digest_date.year, digest_date.month, digest_date.day, tzinfo=timezone.utc),
            Digest.date < datetime(digest_date.year, digest_date.month, digest_date.day + 1, tzinfo=timezone.utc),
        )
    )
    digest = result.scalar_one_or_none()
    if not digest:
        raise HTTPException(status_code=404, detail=f"No digest for {digest_date}")
    return digest
```

- [ ] **Step 4: Create clusters router**

```python
# backend/app/routers/clusters.py
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
```

- [ ] **Step 5: Register both routers in main.py**

```python
from app.routers.digest import router as digest_router
from app.routers.clusters import router as clusters_router

app.include_router(digest_router)
app.include_router(clusters_router)
```

- [ ] **Step 6: Run all tests**

```bash
cd backend
python -m pytest tests/ -v
```

Expected: All passed

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/ backend/tests/test_digest.py backend/app/main.py
git commit -m "feat: add digest and clusters read-only endpoints"
```

---

### Task 9: Chrome bookmark HTML importer

**Files:**
- Create: `backend/scripts/__init__.py`
- Create: `backend/scripts/import_bookmarks.py`
- Create: `backend/tests/test_import_bookmarks.py`
- Create: `backend/tests/fixtures/bookmarks_sample.html`

- [ ] **Step 1: Create sample bookmark HTML fixture**

```html
<!-- backend/tests/fixtures/bookmarks_sample.html -->
<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><H3>Bookmarks Bar</H3>
    <DL><p>
        <DT><A HREF="https://example.com/article1" ADD_DATE="1710000000">Article One</A>
        <DT><A HREF="https://example.com/article2" ADD_DATE="1710100000">Article Two</A>
        <DT><H3>Tech</H3>
        <DL><p>
            <DT><A HREF="https://example.com/nested" ADD_DATE="1710200000">Nested Bookmark</A>
        </DL><p>
    </DL><p>
</DL><p>
```

- [ ] **Step 2: Write tests for the parser**

```python
# backend/tests/test_import_bookmarks.py
from pathlib import Path

from scripts.import_bookmarks import parse_bookmarks_html


def test_parse_bookmarks_html():
    html_path = Path(__file__).parent / "fixtures" / "bookmarks_sample.html"
    bookmarks = parse_bookmarks_html(html_path)
    assert len(bookmarks) == 3
    assert bookmarks[0]["url"] == "https://example.com/article1"
    assert bookmarks[0]["title"] == "Article One"
    assert bookmarks[2]["url"] == "https://example.com/nested"


def test_parse_bookmarks_extracts_timestamp():
    html_path = Path(__file__).parent / "fixtures" / "bookmarks_sample.html"
    bookmarks = parse_bookmarks_html(html_path)
    assert bookmarks[0]["add_date"] == 1710000000
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_import_bookmarks.py -v
```

Expected: FAIL

- [ ] **Step 4: Create the importer script**

```python
# backend/scripts/__init__.py
```

```python
# backend/scripts/import_bookmarks.py
"""
Chrome bookmark HTML importer.

Usage:
    python -m scripts.import_bookmarks path/to/bookmarks.html
"""
import asyncio
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Item, SourceType


class BookmarkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bookmarks = []
        self._current_href = None
        self._current_add_date = None
        self._in_a = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attr_dict = dict(attrs)
            self._current_href = attr_dict.get("href")
            self._current_add_date = attr_dict.get("add_date")
            self._in_a = True

    def handle_data(self, data):
        if self._in_a and self._current_href:
            add_date = int(self._current_add_date) if self._current_add_date else None
            self.bookmarks.append({
                "url": self._current_href,
                "title": data.strip(),
                "add_date": add_date,
            })

    def handle_endtag(self, tag):
        if tag.lower() == "a":
            self._in_a = False
            self._current_href = None
            self._current_add_date = None


def parse_bookmarks_html(path: Path) -> list[dict]:
    parser = BookmarkParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.bookmarks


async def import_to_db(bookmarks: list[dict]):
    async with async_session() as session:
        for bm in bookmarks:
            created_at = (
                datetime.fromtimestamp(bm["add_date"], tz=timezone.utc)
                if bm["add_date"]
                else None
            )
            stmt = (
                insert(Item)
                .values(
                    url=bm["url"],
                    title=bm["title"],
                    source=SourceType.chrome,
                    created_at=created_at,
                )
                .on_conflict_do_nothing(index_elements=["url"])
            )
            await session.execute(stmt)
        await session.commit()
        print(f"Imported {len(bookmarks)} bookmarks")


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.import_bookmarks <bookmarks.html>")
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)
    bookmarks = parse_bookmarks_html(path)
    print(f"Parsed {len(bookmarks)} bookmarks")
    asyncio.run(import_to_db(bookmarks))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/test_import_bookmarks.py -v
```

Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/ backend/tests/test_import_bookmarks.py backend/tests/fixtures/
git commit -m "feat: add Chrome bookmark HTML parser and importer script"
```

---

### Task 10: Manual smoke test — end to end

- [ ] **Step 1: Start the FastAPI server**

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 2: Test POST /api/items**

```bash
curl -X POST http://localhost:8000/api/items \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me" \
  -d '{"url": "https://example.com/test", "title": "Test Article", "source": "chrome"}'
```

Expected: 201 response with item JSON including `"status": "pending"`

- [ ] **Step 3: Test GET /api/items**

```bash
curl http://localhost:8000/api/items
```

Expected: JSON with `items` array containing the item just created

- [ ] **Step 4: Test bookmark import**

```bash
cd backend
python -m scripts.import_bookmarks tests/fixtures/bookmarks_sample.html
```

Expected: "Parsed 3 bookmarks" then "Imported 3 bookmarks"

- [ ] **Step 5: Verify imported bookmarks appear in API**

```bash
curl http://localhost:8000/api/items
```

Expected: `total` of 4 (1 from curl + 3 from import)

- [ ] **Step 6: Run full test suite**

```bash
cd backend
python -m pytest tests/ -v
```

Expected: All tests pass

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "chore: Phase 1 complete — ingest API, schema, and bookmark importer"
git push origin main
```

---

## Phase 1 Completion Checklist

- [ ] Postgres + pgvector running locally with `insight` and `insight_test` databases
- [ ] Alembic migration creates all 4 tables
- [ ] `POST /api/items` creates items with API key auth
- [ ] `POST /api/items` upserts on duplicate URL
- [ ] `GET /api/items` lists items with optional source filter
- [ ] `GET /api/digest/today` and `GET /api/digest/:date` return 404 when empty
- [ ] `GET /api/clusters` returns empty list
- [ ] Bookmark importer parses Chrome HTML and inserts into DB
- [ ] All tests pass
