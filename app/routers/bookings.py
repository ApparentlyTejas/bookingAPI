"""
ACTIVE: step 5 fix attempt 2 (Postgres EXCLUDE constraint) + step 6
idempotency key (see CLAUDE.md build plan).

create_booking() no longer locks the resource row app-side. The overlap
SELECT below is now just an optimistic fast-path (cheap, saves a round trip
for the common non-racing case) — it is NOT what prevents duplicate
bookings. The actual guarantee is the `bookings_no_overlap` EXCLUDE
constraint added in db/002_add_exclusion_constraint.sql: if two concurrent
requests both pass the SELECT and both INSERT, Postgres rejects the second
INSERT at commit time, and we catch that as IntegrityError -> 409. Unlike
step 4's FOR UPDATE lock, this only blocks genuinely overlapping bookings —
non-overlapping requests on the same resource can commit concurrently.

If the client sends idempotency_key, a second submission with the same key
(double-click, retry after a dropped response) returns the original booking
instead of erroring or creating a duplicate — enforced by the
bookings_user_idempotency_key_unique constraint from
db/003_add_idempotency_key.sql, same "app check as fast-path, DB constraint
as guarantee" pattern as the overlap check.

Load testing this under N truly-simultaneous duplicate submissions (same
idempotency_key) surfaced two real bugs, in order of how they were found:

1. A single check-then-insert attempt wasn't enough: a losing transaction
   can fail against a DIFFERENT in-flight competing insert than the one
   that ultimately commits, so an immediate one-shot re-check can run
   before the real winner's row is visible yet, returning a spurious 409
   for what should be a clean idempotent replay. Fixed with a bounded retry
   of the whole check-then-insert sequence (_MAX_ATTEMPTS) — a fresh
   attempt gets a fresh snapshot and almost always resolves cleanly.
2. At the same concurrency level, Postgres occasionally detected an actual
   deadlock while checking the GiST exclusion constraint against several
   uncommitted candidate rows at once (multiple transactions each waiting
   on a lock another one holds), aborting one as the deadlock victim —
   psycopg2.errors.DeadlockDetected / SQLAlchemy OperationalError, not
   IntegrityError, so it was slipping through as an unhandled 500. Now
   caught and retried the same way; if attempts are exhausted this way we
   return 503 (ask the client to retry) rather than 409, since a deadlock
   victim's insert may have been perfectly valid — we don't actually know.

Root cause of both: duplicate submissions of the *same* logical request
were racing each other through the database's general-purpose conflict
machinery, which is built to resolve conflicts between genuinely different
writers, not to coalesce N copies of one writer. The actual fix is
pg_advisory_xact_lock, scoped to hash(user_id, idempotency_key): true
duplicates now serialize on a cheap in-memory lock before ever reaching the
constraint, so only one of them inserts and the rest find it via the
existing-row check once unblocked. This only affects requests sharing the
same key — genuinely different bookings for different users/keys are
completely unaffected and still go through the lock-free constraint path
from step 5. The retry loop stays as defense in depth for the no-key /
different-key overlap case, which can still hit the same two failure modes
under heavy concurrency, just far less often since real overlaps (not
self-duplicates) are the much rarer case in practice.
"""

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Booking, Resource, User
from app.schemas import BookingCreate, BookingOut, MyBookingOut

router = APIRouter(prefix="/bookings", tags=["bookings"])

_MAX_ATTEMPTS = 5


@router.get("", response_model=list[BookingOut])
def list_bookings(
    resource_id: int,
    date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    day_start = datetime.combine(date, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    return (
        db.query(Booking)
        .filter(
            Booking.resource_id == resource_id,
            Booking.start_time < day_end,
            Booking.end_time > day_start,
        )
        .order_by(Booking.start_time)
        .all()
    )


@router.get("/me", response_model=list[MyBookingOut])
def list_my_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(Booking, Resource.name)
        .join(Resource, Resource.id == Booking.resource_id)
        .filter(Booking.user_id == current_user.id)
        .order_by(Booking.start_time.desc())
        .all()
    )
    return [
        MyBookingOut(
            id=booking.id,
            resource_id=booking.resource_id,
            resource_name=resource_name,
            start_time=booking.start_time,
            end_time=booking.end_time,
            created_at=booking.created_at,
        )
        for booking, resource_name in rows
    ]


@router.post("", response_model=BookingOut, status_code=201)
def create_booking(
    payload: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=422, detail="end_time must be after start_time")

    resource = db.query(Resource).filter(Resource.id == payload.resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    for attempt in range(_MAX_ATTEMPTS):
        if payload.idempotency_key:
            # Serializes only duplicate submissions of this exact (user, key) —
            # transaction-scoped, released automatically on commit/rollback.
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"{current_user.id}:{payload.idempotency_key}"},
            )
            existing = (
                db.query(Booking)
                .filter(
                    Booking.user_id == current_user.id,
                    Booking.idempotency_key == payload.idempotency_key,
                )
                .first()
            )
            if existing:
                return existing

        overlap = (
            db.query(Booking)
            .filter(
                Booking.resource_id == payload.resource_id,
                Booking.start_time < payload.end_time,
                Booking.end_time > payload.start_time,
            )
            .first()
        )
        if overlap:
            raise HTTPException(status_code=409, detail="Resource already booked for this time")

        booking = Booking(
            resource_id=payload.resource_id,
            user_id=current_user.id,
            start_time=payload.start_time,
            end_time=payload.end_time,
            idempotency_key=payload.idempotency_key,
        )
        db.add(booking)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if attempt < _MAX_ATTEMPTS - 1:
                continue
            if payload.idempotency_key:
                existing = (
                    db.query(Booking)
                    .filter(
                        Booking.user_id == current_user.id,
                        Booking.idempotency_key == payload.idempotency_key,
                    )
                    .first()
                )
                if existing:
                    return existing
            raise HTTPException(status_code=409, detail="Resource already booked for this time")
        except OperationalError:
            db.rollback()
            if attempt < _MAX_ATTEMPTS - 1:
                continue
            raise HTTPException(
                status_code=503, detail="High contention booking this resource, please retry"
            )
        db.refresh(booking)
        return booking
