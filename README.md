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
docker compose exec db psql -U app -d bookingapi -f /db/002_add_exclusion_constraint.sql
docker compose exec db psql -U app -d bookingapi -f /db/003_add_idempotency_key.sql
docker compose exec db psql -U app -d bookingapi -f /db/004_add_google_calendar.sql
```

Before first run, generate real secrets for `.env` (the checked-in placeholders are dev-only and must not be used anywhere reachable by anyone else):

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"        # -> JWT_SECRET_KEY
python3 -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"  # -> TOKEN_ENCRYPTION_KEY
```

Check it's up:

```bash
curl http://localhost:8000/health
open http://localhost:8000/docs
```

## Calendar UI

A minimal static calendar page is served at `http://localhost:8000/ui/` —
register/log in, pick a resource and date, and click an hourly slot to book
it. A "Resend last booking" button re-submits the same request (same
idempotency key) to demonstrate that a retry returns the original booking
instead of erroring or double-booking.

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

## Admin access

Creating/deleting rooms (`POST`/`DELETE /resources`) and promoting other
users requires `is_admin`, which defaults to `false` for everyone — nobody
is an admin until someone makes them one. Bootstrap the first admin
directly in the database (there's no other way in, by design — an API
endpoint that could self-promote would defeat the point):

```bash
docker compose exec db psql -U app -d bookingapi \
  -c "UPDATE users SET is_admin = true WHERE email = 'you@example.com';"
```

From there, that account can promote/demote anyone else from `/ui/admin.html`
(linked in the header once logged in as an admin) — no more manual SQL
needed. The API refuses to demote the last remaining admin.

## Create a resource and a booking

```bash
TOKEN="<access_token from an admin account>"

curl -X POST http://localhost:8000/resources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Meeting Room A"}'
# -> {"id": 1, ...}

TOKEN="<access_token from any account>"
curl -X POST http://localhost:8000/bookings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"resource_id": 1, "start_time": "2026-09-01T10:00:00Z", "end_time": "2026-09-01T11:00:00Z", "idempotency_key": "<client-generated-uuid>"}'
# idempotency_key is optional. Resubmitting the same key returns the
# original booking instead of erroring or creating a duplicate.

curl "http://localhost:8000/bookings?resource_id=1&date=2026-09-01" \
  -H "Authorization: Bearer $TOKEN"
```

## Running tests

```bash
docker compose exec api pytest -v
```

Runs against a throwaway `bookingapi_test` database in the same Postgres
container (dropped and recreated each run, with all `db/*.sql` migrations
applied) — not SQLite, since the whole point of `test_concurrency.py` is to
prove the actual `EXCLUDE` constraint and advisory-lock behavior work, which
a non-Postgres test double couldn't exercise. That file races 20 concurrent
identical requests at the same slot and asserts exactly one wins, zero
overlaps land in the database — the automated version of the manual Locust
load test below.

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

## Google Calendar sync

Optional. When connected, every booking is silently synced to the user's
Google Calendar (and un-synced on cancel), so Google's own reminder system
handles notifying them — no email infra of our own. It's entirely
best-effort: any Google API failure is caught and logged nowhere, on
purpose, since it must never affect whether a booking succeeds/cancels.

Two ways to connect, same underlying OAuth setup:
- **"Sign in with Google"** on the login screen — for a new visitor, this
  authenticates them (creating an account if their Google email isn't
  registered yet, password field left empty) *and* connects calendar sync
  in one consent screen.
- **"Connect Google Calendar"** in the app sidebar — for a user who's
  already logged in (password or Google) and just wants to add calendar
  sync without changing how they log in.

To enable either:

1. In [Google Cloud Console](https://console.cloud.google.com/), create a
   project (or use an existing one).
2. **APIs & Services > Library** — enable the **Google Calendar API**.
3. **APIs & Services > OAuth consent screen** — choose **External**,
   fill in the required fields (app name, your email). While in "Testing"
   mode you'll need to add your own Google account under **Test users** —
   only those accounts can complete the consent flow until the app is
   published/verified, which isn't needed for personal/small-group use.
4. **APIs & Services > Credentials > Create Credentials > OAuth client ID**
   — type **Web application**. Add an authorized redirect URI matching
   `GOOGLE_REDIRECT_URI` below exactly (`http://localhost:8000/auth/google/callback`
   for local dev; update this — and re-add it here — when you deploy).
5. Copy the generated **Client ID** and **Client secret** into `.env`:
   ```bash
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   ```
6. Restart the API (`docker compose up --build -d api`) — both "Sign in
   with Google" and "Connect Google Calendar" work from there.

Leaving `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` blank disables the
integration cleanly — `/auth/google/login` and `/auth/google/connect` both
return 503, surfaced in the UI as a toast rather than a broken redirect.

## Security notes

- **Rate limited**: `/auth/login` (10/min) and `/auth/register` (5/min) per
  IP, via `slowapi` — see `app/rate_limit.py`.
- **Passwords**: bcrypt-hashed (never stored/logged in plaintext), minimum
  8 characters enforced at the schema level (`app/schemas.py`).
- **Google refresh tokens**: encrypted at rest (Fernet, `app/crypto.py`) —
  a database leak alone doesn't hand out live Calendar access. Requires
  `TOKEN_ENCRYPTION_KEY` to be set; if it changes, previously-connected
  users' tokens become undecryptable and they'll need to reconnect.
- **JWT secret**: must be a real random value in any environment other
  users can reach — see the placeholder warning in `.env.example`.
- Known gaps, if this goes further: no email verification on registration
  (anyone can register with any email address without proving they own it),
  and auth tokens live in `localStorage` rather than an httpOnly cookie
  (standard XSS-vs-CSRF tradeoff for a Bearer-token API; fine as long as
  there's no way to inject arbitrary script, which the app avoids by never
  rendering user-supplied strings via `innerHTML`).
