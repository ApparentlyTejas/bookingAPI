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
- [x] Step 5 (2026-08-07): Fix attempt 2 — Postgres `EXCLUDE USING gist`
      constraint (`resource_id` WITH =, `tstzrange(start_time, end_time)`
      WITH &&) added in `db/002_add_exclusion_constraint.sql`, requires
      `btree_gist` extension for the equality term. Dropped the app-level
      `FOR UPDATE` lock in `app/routers/bookings.py`; the overlap SELECT is
      now just an optimistic fast-path, and the actual guarantee is the
      constraint — a second concurrent INSERT that slips past the SELECT
      fails with `IntegrityError`, caught and returned as 409. Re-ran the
      same racing-same-slot load test: 4448 requests, 1 succeeded, 4447
      correctly got 409, 0 overlapping pairs — same correctness as step 4,
      throughput slightly higher (452 req/s vs 420 req/s), likely because
      Postgres rejects the losing INSERT at commit-time instead of making
      requests queue on a row lock. Surprise: the build plan's own text said
      `tsrange`, but the columns are `TIMESTAMPTZ` — needed `tstzrange`
      instead, `tsrange` would have failed to compile against them.
- [x] Step 6 (2026-08-08): Idempotency key on booking submission
      (`db/003_add_idempotency_key.sql`: `idempotency_key` column + `UNIQUE
      (user_id, idempotency_key)`) and a minimal static calendar UI at
      `/ui/` (`app/static/index.html`, mounted in `app/main.py`, plain
      HTML/CSS/vanilla JS — no build step, no framework). Added `GET
      /bookings?resource_id=&date=` for the UI to know which slots are
      taken. Surprise (the interesting part): stress-testing the
      idempotency key under N truly-simultaneous duplicate submissions
      (same key) surfaced two real concurrency bugs beyond what steps 4-5
      covered — (1) a single check-then-insert attempt could return a
      spurious 409 for a clean retry, because a losing transaction can fail
      against a different in-flight insert than the one that actually
      commits, so an immediate re-check can run before the real winner is
      visible; (2) at the same concurrency level Postgres occasionally hit
      an actual deadlock while validating the GiST exclusion constraint
      against several uncommitted candidates at once, surfacing as
      `OperationalError` (not `IntegrityError`) and slipping through as an
      unhandled 500. Root cause of both: N copies of the *same* logical
      request were racing through conflict machinery meant for genuinely
      different writers. Fixed properly with `pg_advisory_xact_lock`
      scoped to `hash(user_id, idempotency_key)` — true duplicates now
      serialize on a cheap lock before ever reaching the constraint, while
      genuinely different bookings are completely unaffected. Verified: 50
      concurrent identical-key requests (5 runs x 10) all returned the same
      booking, 0 errors; a control run with 10 different keys on the same
      slot still correctly gave 1 success + 9 clean 409s; the original
      step-5 Locust regression (no idempotency key, 30 users/10s) still
      held with 0 overlaps and higher throughput than before (570 req/s).
      UI verified end-to-end in a real headless browser (Playwright):
      register, log in, book a slot, see it turn red/booked, resend the
      same booking and confirm the same booking id comes back. Caught and
      fixed one real UI bug this way — `loadCalendar()` was unconditionally
      re-hiding the "resend" button on every refresh, including the
      refresh triggered by a successful booking, so it never stayed
      visible long enough to click — and one contrast bug (free-slot text
      was invisible white-on-light-green because a generic `button{color:
      white}` rule wasn't overridden for `.slot`).
