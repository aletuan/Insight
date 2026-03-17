from unittest.mock import AsyncMock, patch

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


@pytest.mark.asyncio
async def test_create_item_triggers_enrichment(client):
    """Verify that creating a new item triggers the background enrichment worker."""
    with patch("app.routers.items.trigger_enrichment", new_callable=AsyncMock) as mock_trigger:
        response = await client.post(
            "/api/items",
            json={
                "url": "https://example.com/trigger-test",
                "title": "Trigger Test",
                "source": "chrome",
            },
            headers={"X-API-Key": "change-me"},
        )
        assert response.status_code == 201
        item_id = response.json()["id"]
        mock_trigger.assert_called_once_with(item_id)


@pytest.mark.asyncio
async def test_upsert_does_not_trigger_enrichment(client):
    """Verify that upserting an existing item does NOT re-trigger enrichment."""
    headers = {"X-API-Key": "change-me"}

    with patch("app.routers.items.trigger_enrichment", new_callable=AsyncMock) as mock_trigger:
        await client.post(
            "/api/items",
            json={"url": "https://example.com/upsert-test", "title": "First", "source": "chrome"},
            headers=headers,
        )
        mock_trigger.reset_mock()

        await client.post(
            "/api/items",
            json={"url": "https://example.com/upsert-test", "title": "Updated", "source": "chrome"},
            headers=headers,
        )
        mock_trigger.assert_not_called()


@pytest.mark.asyncio
async def test_search_items_falls_back_to_text_search(client):
    """Test that ?q= falls back to text search if embedding call fails."""
    headers = {"X-API-Key": "change-me"}

    with patch("app.routers.items.trigger_enrichment", new_callable=AsyncMock):
        await client.post(
            "/api/items",
            json={"url": "https://example.com/fallback-test", "title": "Quantum Computing Explained", "source": "chrome"},
            headers=headers,
        )

    with patch("app.routers.items.generate_embedding", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = None  # Embedding fails

        response = await client.get("/api/items?q=Quantum")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert "Quantum" in data["items"][0]["title"]
