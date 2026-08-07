from fastapi import FastAPI
from sqlalchemy import text

from app.database import SessionLocal
from app.routers import auth, bookings, resources

app = FastAPI(title="Booking API")

app.include_router(auth.router)
app.include_router(resources.router)
app.include_router(bookings.router)


@app.get("/health")
def health():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    finally:
        db.close()
