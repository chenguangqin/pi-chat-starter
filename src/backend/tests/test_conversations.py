import pytest

HEADERS_A = {"x-tenant-id": "tenant-a", "x-user-id": "user-1"}
HEADERS_B = {"x-tenant-id": "tenant-b", "x-user-id": "user-2"}


@pytest.mark.asyncio
async def test_create_conversation(client):
    resp = await client.post("/api/conversations", headers=HEADERS_A, json={"title": "Test"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Test"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_conversation_default_title(client):
    resp = await client.post("/api/conversations", headers=HEADERS_A)
    assert resp.status_code == 201
    assert resp.json()["title"] == "New conversation"


@pytest.mark.asyncio
async def test_list_conversations(client):
    await client.post("/api/conversations", headers=HEADERS_A, json={"title": "First"})
    await client.post("/api/conversations", headers=HEADERS_A, json={"title": "Second"})

    resp = await client.get("/api/conversations", headers=HEADERS_A)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["title"] == "Second"
    assert data[1]["title"] == "First"


@pytest.mark.asyncio
async def test_get_conversation(client):
    create_resp = await client.post(
        "/api/conversations", headers=HEADERS_A, json={"title": "My Chat"}
    )
    cid = create_resp.json()["id"]

    resp = await client.get(f"/api/conversations/{cid}", headers=HEADERS_A)
    assert resp.status_code == 200
    assert resp.json()["title"] == "My Chat"


@pytest.mark.asyncio
async def test_rename_conversation(client):
    create_resp = await client.post("/api/conversations", headers=HEADERS_A)
    cid = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/conversations/{cid}", headers=HEADERS_A, json={"title": "Renamed"}
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Renamed"

    get_resp = await client.get(f"/api/conversations/{cid}", headers=HEADERS_A)
    assert get_resp.json()["title"] == "Renamed"


@pytest.mark.asyncio
async def test_delete_conversation(client):
    create_resp = await client.post("/api/conversations", headers=HEADERS_A)
    cid = create_resp.json()["id"]

    resp = await client.delete(f"/api/conversations/{cid}", headers=HEADERS_A)
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/conversations/{cid}", headers=HEADERS_A)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_list_messages_empty(client):
    create_resp = await client.post("/api/conversations", headers=HEADERS_A)
    cid = create_resp.json()["id"]

    resp = await client.get(f"/api/conversations/{cid}/messages", headers=HEADERS_A)
    assert resp.status_code == 200
    assert resp.json() == []


# --- IT-2: Cross-tenant isolation ---


@pytest.mark.asyncio
async def test_cross_tenant_list_isolated(client):
    await client.post("/api/conversations", headers=HEADERS_A, json={"title": "A's conv"})
    resp = await client.get("/api/conversations", headers=HEADERS_B)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_cross_tenant_get_returns_404(client):
    create_resp = await client.post("/api/conversations", headers=HEADERS_A)
    cid = create_resp.json()["id"]

    resp = await client.get(f"/api/conversations/{cid}", headers=HEADERS_B)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_rename_returns_404(client):
    create_resp = await client.post("/api/conversations", headers=HEADERS_A)
    cid = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/conversations/{cid}", headers=HEADERS_B, json={"title": "Hacked"}
    )
    assert resp.status_code == 404

    get_resp = await client.get(f"/api/conversations/{cid}", headers=HEADERS_A)
    assert get_resp.json()["title"] == "New conversation"


@pytest.mark.asyncio
async def test_cross_tenant_delete_returns_404(client):
    create_resp = await client.post("/api/conversations", headers=HEADERS_A)
    cid = create_resp.json()["id"]

    resp = await client.delete(f"/api/conversations/{cid}", headers=HEADERS_B)
    assert resp.status_code == 404

    get_resp = await client.get(f"/api/conversations/{cid}", headers=HEADERS_A)
    assert get_resp.status_code == 200


@pytest.mark.asyncio
async def test_cross_tenant_messages_returns_404(client):
    create_resp = await client.post("/api/conversations", headers=HEADERS_A)
    cid = create_resp.json()["id"]

    resp = await client.get(f"/api/conversations/{cid}/messages", headers=HEADERS_B)
    assert resp.status_code == 404


# --- IT-7: Cross-tenant isolation on EVERY endpoint (opaque body verification) ---


def _assert_opaque_404(resp):
    """Assert 404 with no leaked tenant data in the response body."""
    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body
    for key in ("tenant_id", "user_id", "title", "content", "pi_session_path"):
        assert key not in body, f"Response body leaked field '{key}'"


@pytest.mark.asyncio
async def test_it7_cross_tenant_get_conversation_opaque(client):
    create_resp = await client.post(
        "/api/conversations", headers=HEADERS_A, json={"title": "Secret Title"}
    )
    cid = create_resp.json()["id"]

    resp = await client.get(f"/api/conversations/{cid}", headers=HEADERS_B)
    _assert_opaque_404(resp)
    assert "Secret Title" not in resp.text


@pytest.mark.asyncio
async def test_it7_cross_tenant_rename_opaque(client):
    create_resp = await client.post("/api/conversations", headers=HEADERS_A)
    cid = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/conversations/{cid}", headers=HEADERS_B, json={"title": "Hacked"}
    )
    _assert_opaque_404(resp)


@pytest.mark.asyncio
async def test_it7_cross_tenant_delete_opaque(client):
    create_resp = await client.post("/api/conversations", headers=HEADERS_A)
    cid = create_resp.json()["id"]

    resp = await client.delete(f"/api/conversations/{cid}", headers=HEADERS_B)
    _assert_opaque_404(resp)

    get_resp = await client.get(f"/api/conversations/{cid}", headers=HEADERS_A)
    assert get_resp.status_code == 200


@pytest.mark.asyncio
async def test_it7_cross_tenant_get_messages_opaque(client):
    create_resp = await client.post("/api/conversations", headers=HEADERS_A)
    cid = create_resp.json()["id"]

    resp = await client.get(f"/api/conversations/{cid}/messages", headers=HEADERS_B)
    _assert_opaque_404(resp)


@pytest.mark.asyncio
async def test_it7_cross_tenant_send_message_returns_404(client):
    """POST /api/conversations/{id}/messages with wrong tenant → 404, opaque body."""
    create_resp = await client.post("/api/conversations", headers=HEADERS_A)
    cid = create_resp.json()["id"]

    resp = await client.post(
        f"/api/conversations/{cid}/messages",
        headers=HEADERS_B,
        json={"content": "cross-tenant probe"},
    )
    _assert_opaque_404(resp)
