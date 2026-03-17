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
