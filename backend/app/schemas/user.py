from pydantic import BaseModel, ConfigDict
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
    # password si lo vamos a requerir o logeo por telegram directo

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
