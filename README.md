# booking-api

Concurrency-safe resource booking API. See [CLAUDE.md](./CLAUDE.md) for the
project story and build plan.

Note: Postgres is exposed on host port **5434** (not 5432), since a native
Postgres was already using 5432 (and 5433) on this machine. `docker compose
exec` commands below go straight into the container and are unaffected.

## Setup

```bash
docker compose up --build
```

Then apply the schema manually (not auto-run — see CLAUDE.md conventions):

```bash
docker compose exec db psql -U app -d bookingapi -f /db/001_schema.sql
```

Check it's up:

```bash
curl http://localhost:8000/health
open http://localhost:8000/docs
```

## Auth flow

```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test-password-123"}'

# Login (OAuth2 password flow — form-encoded, not JSON)
curl -X POST http://localhost:8000/auth/login \
  -d "username=test@example.com&password=test-password-123"
# -> {"access_token": "...", "token_type": "bearer"}
```

## Create a resource and a booking

```bash
TOKEN="<access_token from login>"

curl -X POST http://localhost:8000/resources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Meeting Room A"}'
# -> {"id": 1, ...}

curl -X POST http://localhost:8000/bookings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"resource_id": 1, "start_time": "2026-09-01T10:00:00Z", "end_time": "2026-09-01T11:00:00Z"}'
```

## Load test (step 3 — reproduce the race condition)

```bash
pip install locust
TEST_EMAIL=test@example.com TEST_PASSWORD=test-password-123 RESOURCE_ID=1 \
  locust -f loadtest/locustfile.py --headless -u 30 -r 30 -t 10s \
  --host http://localhost:8000
```

Then check for overlapping bookings — the verification query lives at the
bottom of `db/001_schema.sql`:

```bash
docker compose exec db psql -U app -d bookingapi
```
