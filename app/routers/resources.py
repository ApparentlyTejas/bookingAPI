from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Resource, User
from app.schemas import ResourceCreate, ResourceOut

router = APIRouter(prefix="/resources", tags=["resources"])


@router.post("", response_model=ResourceOut, status_code=201)
def create_resource(
    payload: ResourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resource = Resource(name=payload.name, description=payload.description)
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


@router.get("", response_model=list[ResourceOut])
def list_resources(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Resource).all()


@router.get("/{resource_id}", response_model=ResourceOut)
def get_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource
