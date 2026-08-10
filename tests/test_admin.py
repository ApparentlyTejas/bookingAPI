from tests.conftest import register_and_login


def test_non_admin_cannot_list_users(client, user_headers):
    resp = client.get("/admin/users", headers=user_headers)
    assert resp.status_code == 403


def test_admin_can_list_users(client, admin_headers, user_headers):
    resp = client.get("/admin/users", headers=admin_headers)
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert "admin@example.com" in emails
    assert "user@example.com" in emails


def test_admin_can_promote_user(client, admin_headers):
    token = register_and_login(client, "newperson@example.com")
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.patch(f"/admin/users/{me['id']}", json={"is_admin": True}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is True


def test_cannot_demote_only_remaining_admin(client, admin_headers):
    me = client.get("/auth/me", headers=admin_headers).json()
    resp = client.patch(f"/admin/users/{me['id']}", json={"is_admin": False}, headers=admin_headers)
    assert resp.status_code == 400


def test_can_demote_admin_if_another_remains(client, admin_headers):
    token = register_and_login(client, "secondadmin@example.com")
    second = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    client.patch(f"/admin/users/{second['id']}", json={"is_admin": True}, headers=admin_headers)

    me = client.get("/auth/me", headers=admin_headers).json()
    resp = client.patch(f"/admin/users/{me['id']}", json={"is_admin": False}, headers=admin_headers)
    assert resp.status_code == 200


def test_non_admin_cannot_view_analytics(client, user_headers):
    resp = client.get("/admin/analytics", headers=user_headers)
    assert resp.status_code == 403


def test_analytics_reflects_bookings(client, admin_headers, user_headers, resource_id):
    client.post(
        "/bookings",
        json={
            "resource_id": resource_id,
            "start_time": "2027-01-01T10:00:00Z",
            "end_time": "2027-01-01T11:00:00Z",
        },
        headers=user_headers,
    )
    resp = client.get("/admin/analytics", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_bookings"] == 1
    assert body["upcoming_bookings"] == 1
    assert body["busiest_rooms"] == [{"resource_name": "Test Room", "bookings": 1}]
    assert body["busiest_hours"] == [{"hour": 10, "bookings": 1}]
