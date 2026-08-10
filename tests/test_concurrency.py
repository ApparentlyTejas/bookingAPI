"""
Automates the manual verification from CLAUDE.md's build plan (step 3's
Locust load test + the psql overlap-check query) as a real pytest test:
race N concurrent identical requests at the same slot and assert exactly
one wins, using nothing but the bookings_no_overlap EXCLUDE constraint from
db/002_add_exclusion_constraint.sql — no app-level lock.

This is the test that actually proves the concurrency story, not just the
individual-request behavior tests in test_bookings.py.
"""

import concurrent.futures

from sqlalchemy import text

from tests.conftest import register_and_login

N_CONCURRENT = 20


def test_concurrent_identical_bookings_exactly_one_wins(client, admin_headers, resource_id):
    token = register_and_login(client, "racer@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "resource_id": resource_id,
        "start_time": "2027-03-01T10:00:00Z",
        "end_time": "2027-03-01T11:00:00Z",
    }

    def attempt(_):
        return client.post("/bookings", json=payload, headers=headers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=N_CONCURRENT) as pool:
        results = list(pool.map(attempt, range(N_CONCURRENT)))

    statuses = [r.status_code for r in results]
    assert statuses.count(201) == 1, f"expected exactly one booking to succeed, got: {statuses}"
    assert statuses.count(409) == N_CONCURRENT - 1

    from app.database import SessionLocal

    session = SessionLocal()
    overlaps = session.execute(
        text(
            """
            SELECT count(*) FROM bookings a
            JOIN bookings b ON a.resource_id = b.resource_id AND a.id < b.id
            WHERE a.start_time < b.end_time AND b.start_time < a.end_time
            """
        )
    ).scalar()
    session.close()
    assert overlaps == 0, "the exclusion constraint let overlapping bookings land"


def test_concurrent_identical_idempotency_key_all_return_same_booking(client, resource_id):
    # This is the specific race documented in bookings.py's docstring: N
    # duplicate submissions of the *same* logical request (same key) should
    # all resolve to one booking, never a spurious 409, via the
    # pg_advisory_xact_lock + retry-loop combination.
    token = register_and_login(client, "replay@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "resource_id": resource_id,
        "start_time": "2027-03-02T10:00:00Z",
        "end_time": "2027-03-02T11:00:00Z",
        "idempotency_key": "same-key-for-everyone",
    }

    def attempt(_):
        return client.post("/bookings", json=payload, headers=headers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=N_CONCURRENT) as pool:
        results = list(pool.map(attempt, range(N_CONCURRENT)))

    statuses = [r.status_code for r in results]
    assert all(s == 201 for s in statuses), f"expected all 201s for a shared idempotency key, got: {statuses}"

    booking_ids = {r.json()["id"] for r in results}
    assert len(booking_ids) == 1, f"expected one booking id, got {booking_ids}"


def test_concurrent_different_resources_all_succeed(client, admin_headers):
    # Sanity check on the flip side: concurrency shouldn't cause false
    # rejections when there's genuinely no conflict.
    resource_ids = [
        client.post("/resources", json={"name": f"Room {i}"}, headers=admin_headers).json()["id"]
        for i in range(N_CONCURRENT)
    ]
    token = register_and_login(client, "parallel@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    def attempt(rid):
        return client.post(
            "/bookings",
            json={
                "resource_id": rid,
                "start_time": "2027-03-03T10:00:00Z",
                "end_time": "2027-03-03T11:00:00Z",
            },
            headers=headers,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=N_CONCURRENT) as pool:
        results = list(pool.map(attempt, resource_ids))

    assert all(r.status_code == 201 for r in results)
