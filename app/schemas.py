from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict


class UserRegister(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ResourceCreate(BaseModel):
    name: str
    description: str | None = None


class ResourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime


class BookingCreate(BaseModel):
    resource_id: int
    start_time: datetime
    end_time: datetime


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resource_id: int
    user_id: int
    start_time: datetime
    end_time: datetime
    created_at: datetime
