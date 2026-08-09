"""
Admin-only user management: list users, promote/demote is_admin. Resource
create/delete lives in app/routers/resources.py (same require_admin guard)
since those endpoints are already under /resources; this router is just for
managing who has that access in the first place.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.schemas import AdminUserRoleUpdate, UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return db.query(User).order_by(User.created_at).all()


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user_role(
    user_id: int,
    payload: AdminUserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id and not payload.is_admin:
        remaining_admins = db.query(User).filter(User.is_admin.is_(True), User.id != user.id).count()
        if remaining_admins == 0:
            raise HTTPException(status_code=400, detail="Can't remove the only remaining admin")

    user.is_admin = payload.is_admin
    db.commit()
    db.refresh(user)
    return user
