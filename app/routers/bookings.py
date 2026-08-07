"""
ACTIVE: step 5 fix attempt 2 — Postgres EXCLUDE constraint (see CLAUDE.md
build plan).

create_booking() no longer locks the resource row app-side. The overlap
SELECT below is now just an optimistic fast-path (cheap, saves a round trip
for the common non-racing case) — it is NOT what prevents duplicate
bookings. The actual guarantee is the `bookings_no_overlap` EXCLUDE
constraint added in db/002_add_exclusion_constraint.sql: if two concurrent
requests both pass the SELECT and both INSERT, Postgres rejects the second
INSERT at commit time, and we catch that as IntegrityError -> 409. Unlike
step 4's FOR UPDATE lock, this only blocks genuinely overlapping bookings —
non-overlapping requests on the same resource can commit concurrently.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Booking, Resource, User
from app.schemas import BookingCreate, BookingOut

router = APIRouter(prefix="/bookings", tags=["bookings"])


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
    )
    db.add(booking)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Resource already booked for this time")
    db.refresh(booking)
    return booking
