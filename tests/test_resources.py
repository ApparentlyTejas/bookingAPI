def test_non_admin_cannot_create_resource(client, user_headers):
    resp = client.post("/resources", json={"name": "Sneaky Room"}, headers=user_headers)
    assert resp.status_code == 403


def test_admin_can_create_resource(client, admin_headers):
    resp = client.post("/resources", json={"name": "Meeting Room A"}, headers=admin_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Meeting Room A"
    assert body["capacity"] is None
    assert body["amenities"] == []


def test_create_resource_with_capacity_and_amenities(client, admin_headers):
    resp = client.post(
        "/resources",
        json={"name": "Board Room", "capacity": 12, "amenities": ["Projector", "Whiteboard"]},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["capacity"] == 12
    assert body["amenities"] == ["Projector", "Whiteboard"]


def test_create_resource_rejects_non_positive_capacity(client, admin_headers):
    resp = client.post("/resources", json={"name": "Room", "capacity": 0}, headers=admin_headers)
    assert resp.status_code == 422


def test_list_resources_open_to_any_authed_user(client, admin_headers, user_headers):
    client.post("/resources", json={"name": "Meeting Room A"}, headers=admin_headers)
    resp = client.get("/resources", headers=user_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_non_admin_cannot_delete_resource(client, admin_headers, user_headers):
    resource = client.post("/resources", json={"name": "Room"}, headers=admin_headers).json()
    resp = client.delete(f"/resources/{resource['id']}", headers=user_headers)
    assert resp.status_code == 403


def test_admin_can_delete_unused_resource(client, admin_headers):
    resource = client.post("/resources", json={"name": "Room"}, headers=admin_headers).json()
    resp = client.delete(f"/resources/{resource['id']}", headers=admin_headers)
    assert resp.status_code == 204
    assert client.get(f"/resources/{resource['id']}", headers=admin_headers).status_code == 404


def test_cannot_delete_resource_with_bookings(client, admin_headers, user_headers):
    resource = client.post("/resources", json={"name": "Room"}, headers=admin_headers).json()
    client.post(
        "/bookings",
        json={
            "resource_id": resource["id"],
            "start_time": "2027-01-01T10:00:00Z",
            "end_time": "2027-01-01T11:00:00Z",
        },
        headers=user_headers,
    )
    resp = client.delete(f"/resources/{resource['id']}", headers=admin_headers)
    assert resp.status_code == 409
