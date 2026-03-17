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
