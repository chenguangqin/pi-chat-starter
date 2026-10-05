import pytest


@pytest.mark.asyncio
async def test_missing_tenant_id_returns_401(client):
    resp = await client.get("/api/conversations", headers={"x-user-id": "user-1"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_user_id_returns_401(client):
    resp = await client.get("/api/conversations", headers={"x-tenant-id": "tenant-a"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_empty_headers_returns_401(client):
    resp = await client.get(
        "/api/conversations", headers={"x-tenant-id": "", "x-user-id": ""}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_no_headers_returns_401(client):
    resp = await client.get("/api/conversations")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_headers_pass_through(client):
    resp = await client.get(
        "/api/conversations",
        headers={"x-tenant-id": "tenant-a", "x-user-id": "user-1"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_endpoint_needs_no_auth(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
