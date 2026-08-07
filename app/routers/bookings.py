"""
ACTIVE: step 2 naive check-then-insert (see CLAUDE.md build plan).

create_booking() below is intentionally racy: it SELECTs for an overlapping
booking, then INSERTs, as two separate statements with no row lock in
between. Under concurrent requests for the same resource/timeslot, two
requests can both pass the overlap check before either commits, producing
duplicate/overlapping bookings. This is deliberate — see CLAUDE.md step 3
(load test to confirm) and steps 4-5 (the two fixes).
"""

from fastapi import APIRouter, Depends, HTTPException
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
    db.commit()
    db.refresh(booking)
    return booking
