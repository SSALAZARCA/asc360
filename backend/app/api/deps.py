from fastapi import Header, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional
import uuid

from app.core.security import decode_access_token
from app.database import get_db


class CurrentUser:
    """Contenedor simple para los datos del usuario autenticado extraídos del JWT."""
    def __init__(self, user_id: str, role: str, tenant_id: Optional[str]):
        self.user_id = user_id
        self.role = role
        self.tenant_id = uuid.UUID(tenant_id) if tenant_id else None

    @property
    def is_superadmin(self) -> bool:
        return self.role == "superadmin"

    @property
    def is_admin(self) -> bool:
        return self.role in ("superadmin", "jefe_taller")

    @property
    def is_proveedor(self) -> bool:
        return self.role == "proveedor"

    @property
    def is_imports_editor(self) -> bool:
        return self.role in ("superadmin", "proveedor")


async def get_current_user(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = None
) -> CurrentUser:
    """
    Dependencia central de autenticación.
    Extrae y valida el JWT del header 'Authorization: Bearer <token>' 
    o del query param '?token=<token>' (útil para descargar archivos).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autenticado. Token de acceso requerido.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    actual_token = None
    if token:
        actual_token = token
    elif authorization and authorization.startswith("Bearer "):
        actual_token = authorization.split(" ", 1)[1]
    else:
        raise credentials_exception

    payload = decode_access_token(actual_token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado. Por favor inicie sesión nuevamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    role = payload.get("role")
    tenant_id = payload.get("tenant_id")

    if not user_id or not role:
        raise credentials_exception

    return CurrentUser(user_id=user_id, role=role, tenant_id=tenant_id)


async def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[CurrentUser]:
    """
    Dependencia opcional: no lanza excepción si no hay token (para endpoints internos del bot Sonia).
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    role = payload.get("role")
    tenant_id = payload.get("tenant_id")
    if not user_id or not role:
        return None
    return CurrentUser(user_id=user_id, role=role, tenant_id=tenant_id)



