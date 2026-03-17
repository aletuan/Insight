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
