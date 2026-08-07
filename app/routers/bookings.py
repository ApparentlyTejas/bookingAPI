"""
ACTIVE: step 4 fix attempt 1 — SELECT ... FOR UPDATE row lock (see CLAUDE.md
build plan).

create_booking() locks the resource row before checking for an overlap, so
only one transaction at a time can be mid-overlap-check for a given
resource_id — concurrent requests for the same resource block on the lock
and see each other's commits. This closes the race from step 2/3, but it
serializes ALL bookings on that resource, not just overlapping ones: two
requests for non-overlapping timeslots on the same resource still queue up
behind each other. See CLAUDE.md step 5 for the alternative (exclusion
constraint) that only serializes actual overlaps.
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

    resource = (
        db.query(Resource)
        .filter(Resource.id == payload.resource_id)
        .with_for_update()
        .first()
    )
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
