from pydantic import BaseModel, ConfigDict, EmailStr
from typing import Optional
from uuid import UUID

from app.models.user import Role, UserStatus

# Base (compartido)
class UserBase(BaseModel):
    name: str
    telegram_id: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Role
    status: Optional[UserStatus] = UserStatus.pending
    service_center_name: Optional[str] = None

# Para crear
class UserCreate(UserBase):
    tenant_id: Optional[UUID] = None
    password: Optional[str] = None
    # Cedula, used only to dedup an existing `role=client` row before
    # inserting a new one (service reception "isNew" flow). See
    # `create_user`'s identification lookup.
    identification: Optional[str] = None
    # sdd/reception-email-notification (ADR 7): overridden here only, NOT
    # on `UserBase` -- `UserBase` also backs `UserOut`/admin reads, where
    # retroactive strictness could 422 rows that already exist with a
    # malformed/legacy email value. Only the creation path validates.
    email: Optional[EmailStr] = None

# Para actualizar
class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    telegram_id: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[Role] = None
    tenant_id: Optional[UUID] = None

class UserStatusUpdate(BaseModel):
    status: UserStatus

# Para respuesta (Out)
class UserOut(UserBase):
    id: UUID
    tenant_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)
