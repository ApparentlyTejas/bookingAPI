# Project instructions

Concurrency-safe resource booking API — a portfolio project for backend
Werkstudent/internship applications. FastAPI + PostgreSQL + Docker. Solo
build, ~10 days, alongside a Master's course load.

## What this project is for

The point is not a polished product. The point is a defensible, specific
story about a concurrency bug: found it via load testing, fixed it two
ways, can explain the tradeoff between the two fixes in a technical
interview. Don't add features that don't serve that story. Scope
creep (notifications, recurring bookings, admin dashboard, waitlists) is
explicitly out of scope until after the core story is shipped and
committed.

## The build plan

1. Schema + auth + basic resource CRUD.
2. Naive `POST /bookings`: check-then-insert. (Already scaffolded, active
   in `app/routers/bookings.py`.)
3. Load test the naive version (`loadtest/locustfile.py`) against a
   single slot with concurrent requests. Confirm overlapping bookings
   land in the DB using the verification query in `db/001_schema.sql`.
4. Fix attempt 1: lock the resource row with `SELECT ... FOR UPDATE`
   before checking. Re-run the load test. Note it serializes ALL
   bookings on that resource, not just overlapping ones.
5. Fix attempt 2: apply `db/002_add_exclusion_constraint.sql` (Postgres
   `EXCLUDE USING gist` on `resource_id` + `tsrange(start_time,
   end_time)`). Drop the app-level lock. Re-run the load test, compare
   throughput and correctness against attempt 1.
6. Minimal calendar UI + idempotency key on booking submission.
7. Deploy, share with real users (uni dorm/Fachschaft), fix what breaks.

Track progress by checking off steps here as they're completed, and
note the date + any surprises under each one.

## Conventions

- Commit each fix attempt (step 2, 4, 5) as its own commit with a clear
  message. The git history is meant to be readable as the interview
  story — don't squash these together.
- Schema changes go in a new numbered file under `db/`, applied
  manually (see README) — not auto-run, and not done via
  `Base.metadata.create_all()`.
- Keep `app/routers/bookings.py`'s docstring in sync with whichever
  attempt is currently active.
- When in doubt about scope, prefer the smaller change that still
  produces a measurable, explainable result over a more "complete"
  feature.

## Current status

- [x] Step 1 (2026-08-07): Schema + auth (JWT via python-jose, bcrypt
      hashing) + resources CRUD scaffolded. FastAPI + SQLAlchemy +
      Postgres 16 via docker-compose. Schema applied manually via
      `db/001_schema.sql`, not `Base.metadata.create_all()`.
- [x] Step 2 (2026-08-07): Naive `POST /bookings` (check-then-insert, no
      locking) scaffolded and active in `app/routers/bookings.py`.
- [x] Step 3 (2026-08-07): Load tested naive `POST /bookings` with Locust
      (50 concurrent users, same resource_id + timeslot, pre-fetched shared
      token to avoid login latency staggering requests). Confirmed the race:
      4 overlapping bookings (ids 3-6) landed for the same resource+slot in
      the same millisecond. Verification query in `db/001_schema.sql`
      returned 6 overlapping pairs (C(4,2)). Surprise: an early attempt with
      per-user login in `on_start` showed almost no race (bcrypt hashing
      staggered each user's first request enough to avoid overlap) — had to
      pre-fetch a single token and pass it via env var to get true
      simultaneous requests.
- [x] Step 4 (2026-08-07): Fix attempt 1 — `SELECT ... FOR UPDATE` on the
      resource row before the overlap check, active in
      `app/routers/bookings.py`. Re-ran the same load test (30 users, same
      resource+slot, 10s): 4128 requests, 4127 got `409 Conflict`, 1
      succeeded. Verification query returned 0 overlapping pairs (down from
      6). Confirmed the documented tradeoff: the lock is on the resource
      row, not the timeslot, so it serializes every booking attempt on that
      resource — including non-overlapping ones — not just conflicting
      requests. (Tried to demonstrate this with a small concurrent,
      non-overlapping-timeslot benchmark; inconclusive at n=20 because
      Python thread/HTTP overhead per request, ~80-100ms, swamped the
      actual lock-wait time. The serialization is provable from the SQL
      semantics — `FOR UPDATE` holds the row lock until commit, so any two
      transactions touching the same `resource_id` block each other
      regardless of time range — without needing a clean benchmark.)
