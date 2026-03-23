import pytest


@pytest.mark.asyncio
async def test_create_and_list_notifications(client):
    create_resp = await client.post(
        "/notifications",
        json={
            "title": "Статус изменен",
            "message": "Суд принял документы",
            "notification_type": "court_filing",
            "severity": "high",
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["is_read"] is False
    assert created["severity"] == "high"

    list_resp = await client.get("/notifications")
    assert list_resp.status_code == 200
    notifications = list_resp.json()
    assert len(notifications) >= 1
    assert notifications[0]["id"] == created["id"]


@pytest.mark.asyncio
async def test_mark_notification_as_read(client):
    create_resp = await client.post(
        "/notifications",
        json={
            "title": "Новый документ",
            "message": "Документ отправлен в канцелярию",
            "severity": "medium",
        },
    )
    notification_id = create_resp.json()["id"]
    patch_resp = await client.patch(f"/notifications/{notification_id}/read")
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_read"] is True
    assert patch_resp.json()["read_at"] is not None


@pytest.mark.asyncio
async def test_mark_notification_not_found(client):
    response = await client.patch("/notifications/999999/read")
    assert response.status_code == 404
    assert response.json()["detail"] == "Notification not found"


@pytest.mark.asyncio
async def test_openapi_contains_notifications_paths(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/notifications" in paths
    assert "/notifications/{notification_id}/read" in paths
