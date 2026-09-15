"""
Motored Pedidos — capa de base de datos.

Módulo hermano de `app.database`, completamente aislado (sdd/motored-
pedidos-cimientos, ADR-4 y ADR-5): base declarativa propia, engine propio,
sesión propia. Este módulo NUNCA importa nada de `app.database` ni comparte
su `Base`/metadata.
"""
from functools import lru_cache
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.config import settings

# Base declarativa independiente de `app.database.Base`. Los modelos
# Motored (Fase 3) heredan de esta, nunca de la de asc360.
MotoredBase = declarative_base()


@lru_cache(maxsize=1)
def get_motored_engine():
    """
    Construye el engine async de Motored de forma PEREZOSA (lazy).

    CRÍTICO (ADR-4): importar este módulo — y por lo tanto `app.main.app`
    una vez que una fase futura monte el router de Motored — NUNCA debe
    crear un engine ni intentar conectarse a nada, incluso si
    `MOTORED_DATABASE_URL` está vacío o mal configurado. `tests/conftest.py`
    importa `app.main.app`, así que un engine eager rompería toda la suite
    existente de asc360 en cuanto este módulo se importe.

    El cacheo (`lru_cache`) además garantiza un único engine por proceso,
    igual que el patrón singleton de `app.database.engine`.
    """
    return create_async_engine(
        settings.MOTORED_DATABASE_URL,
        echo=False,
        future=True,
    )


def motored_session_maker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        get_motored_engine(), class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


async def get_motored_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependencia FastAPI para Motored.

    A diferencia de `app.database.get_db` (que hace `commit()` automático
    al salir limpio), esta NO hace commit implícito (ADR-5): el caller /
    capa de servicio decide explícitamente cuándo persistir. Esto es
    indispensable para la carga masiva todo-o-nada (Fase 3/4) — sin esto,
    "no se escribió nada" no sería demostrable. Solo hace rollback
    explícito ante una excepción; en una salida limpia sin `commit()`, la
    sesión se cierra y el pool descarta la transacción pendiente.
    """
    session_maker = motored_session_maker()
    async with session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
