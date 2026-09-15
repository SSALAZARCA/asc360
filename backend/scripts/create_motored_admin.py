"""
Motored Pedidos — bootstrap del primer usuario ADMIN
(sdd/motored-pedidos-cimientos, Fase 5).

Mirrors `create_superadmin.py`'s exact idempotency pattern (check-by-email,
create only if absent, never touch an existing row) and CLI shape (async
function + `asyncio.run` en `__main__`, `sys.path` insertado para poder
correrlo standalone), pero apunta a la base de datos AISLADA de Motored
(`app.motored.database`) y al modelo `Usuario` de ese módulo -- CERO
relación con `app.models.user.User` / la base de asc360.

Diferencia deliberada frente a `create_superadmin.py` (que hardcodea
"admin123"): la contraseña NUNCA se hardcodea ni se loguea (proposal,
"Security Constraints" -- "The ADMIN bootstrap script must never hardcode
or log a password"). Se toma de la variable de entorno
`MOTORED_ADMIN_PASSWORD` (para provisioning no interactivo) o, si no está
seteada, se pide de forma interactiva con `getpass` (no se muestra en
pantalla).
"""
import asyncio
import getpass
import os
import sys

# Añadir el raíz del proyecto al PYTHONPATH (mismo patrón que create_superadmin.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.motored.database import motored_session_maker  # noqa: E402
from app.motored.models.usuario import MotoredRole, Usuario  # noqa: E402

ADMIN_NOMBRE = "asalazar"
ADMIN_EMAIL = "asalazarc@motoredcolombia.com.co"


def _resolve_password() -> str:
    """Nunca hardcodeada, nunca logueada. Prioriza la variable de entorno
    (provisioning no interactivo / CI); si no está seteada, la pide de forma
    interactiva sin eco en pantalla."""
    env_password = os.environ.get("MOTORED_ADMIN_PASSWORD")
    if env_password:
        return env_password
    return getpass.getpass("Contraseña para el ADMIN de Motored (asalazar): ")


async def create_motored_admin() -> None:
    if not settings.MOTORED_DATABASE_URL:
        print(
            "ERROR: MOTORED_DATABASE_URL no está configurada. "
            "Configurá esa variable de entorno apuntando a la base de datos "
            "de Motored antes de correr este script."
        )
        raise SystemExit(1)

    session_maker = motored_session_maker()
    async with session_maker() as session:
        # Si ya existe un usuario con este email, no crear ni modificar nada
        # -- ni la contraseña, ni el rol, ni ningún otro campo.
        stmt = select(Usuario).where(Usuario.email == ADMIN_EMAIL)
        res = await session.execute(stmt)
        existing = res.scalars().first()

        if existing:
            print(f"Ya existe un usuario Motored con email {ADMIN_EMAIL}. No se modifica.")
            return

        password = _resolve_password()
        admin = Usuario(
            nombre=ADMIN_NOMBRE,
            email=ADMIN_EMAIL,
            hashed_password=get_password_hash(password),
            role=MotoredRole.ADMIN,
            activo=True,
        )
        session.add(admin)
        await session.commit()
        print(f"ADMIN de Motored {ADMIN_EMAIL} creado exitosamente.")


if __name__ == "__main__":
    asyncio.run(create_motored_admin())
