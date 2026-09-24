"""
Motored Pedidos — vinculación de Telegram para notificaciones ADMIN
(sdd/motored-ventas-perdidas-bot, Phase 4 "Approval service + Usuarios UI",
design D5 "Telegram linking").

Un código de un solo uso, de 8 caracteres, generado con `secrets.choice`
sobre un alfabeto de 32 caracteres SIN `0`/`O`/`1`/`I` (design D5 lo
describe como "31 caracteres" -- son 32: 8 dígitos + 24 letras del
alfabeto SIN esos 4 ambiguos; conteo corregido acá, alfabeto sin cambios --
post-Phase-4 review) -- evita confusión al transcribir a mano desde la
pantalla web al bot. Solo el hash sha256 del código se persiste
(`Usuario.codigo_vinculacion_hash`) -- el código en claro nunca toca la
base de datos, mismo criterio que un password. TTL de 10 minutos
(`Usuario.codigo_vinculacion_expira`).

`generar_codigo_vinculacion` es el lado WEB (este Phase, `POST /usuarios/
me/telegram/codigo`, ADMIN únicamente sobre SU PROPIA fila -- spec "ADMIN
telegram-linking independent of role": ningún endpoint de este Phase deja
vincular la cuenta de OTRO usuario). `consumir_codigo_vinculacion` es una
función de servicio pura, lista para que Fase 5 (`POST /admin/vincular`,
task 5.9) la use desde el router del bot -- no tiene un endpoint propio
todavía en este Phase (el único consumidor real de un código es el bot, y
`deps_bot.py`/el router del bot son responsabilidad de Fase 5); se
construye ahora, ya probada, para que Fase 5 solo tenga que conectar un
endpoint encima, sin reinventar el hashing/expiración/single-use.

`consumir_codigo_vinculacion` usa un claim atómico (post-Phase-4 review,
finding #2), el MISMO patrón que `services/solicitudes.py::
resolver_solicitud` (este mismo Phase) y `services/demanda_perdida_bot.py::
_reclamar_anulacion` (Fase 3): un `UPDATE ... WHERE codigo_vinculacion_hash
= :hash AND codigo_vinculacion_expira > :ahora RETURNING id` -- sin este
claim, dos cuentas de Telegram distintas presentando el MISMO código
todavía vigente casi al mismo tiempo podían pasar ambas el SELECT+chequeo
de expiración antes de que cualquiera hiciera commit, y la segunda escritura
podía pisar en silencio el `telegram_id` que la primera ya había fijado.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.usuario import Usuario

# Sin 0/O/1/I (design D5) -- 32 caracteres (8 dígitos + 24 letras); el
# design la describe como "31-character alphabet", pero contando de nuevo
# son 32 -- ver el docstring del módulo.
_ALFABETO = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_LARGO_CODIGO = 8
_TTL_MINUTOS = 10


class CodigoVinculacionInvalidoError(Exception):
    """El código presentado no matchea ningún hash vigente, o el que
    matcheó ya expiró -- excepción de dominio propia, traducida a un 4xx
    en la capa de API/bot (Fase 5), nunca levantada directamente contra el
    cliente. Mismo criterio que `SolicitudYaResuelta`/`CargaYaAnuladaError`:
    no distingue "no existe" de "expiró" en el tipo de excepción, ambos son
    igual de inválidos para quien presentó el código."""


class UsuarioNoEncontradoTrasClaim(Exception):
    """El claim atómico afectó una fila, pero el `SELECT` posterior no
    encontró ningún `Usuario` con ese id -- mismo caso, mismo criterio, que
    `services/solicitudes.py::UsuarioNoEncontradoTrasClaim` (post-Phase-4
    review, finding #3, gga follow-up: el fix se había aplicado ahí pero no
    acá, mismo tipo de bug). Hoy inalcanzable en la práctica (no existe un
    camino de hard-delete para `Usuario`), pero `consumir_codigo_
    vinculacion` es la función que Fase 5 llamará desde el router del bot,
    así que este caso debe fallar RUIDOSAMENTE ACÁ -- antes de que
    cualquier caller haga `commit()` -- en vez de devolver `None` en
    silencio."""


def _hashear(codigo: str) -> str:
    return hashlib.sha256(codigo.encode("utf-8")).hexdigest()


def _generar_codigo_crudo() -> str:
    return "".join(secrets.choice(_ALFABETO) for _ in range(_LARGO_CODIGO))


async def generar_codigo_vinculacion(db: AsyncSession, usuario: Usuario) -> str:
    """Genera un código nuevo para `usuario` (una fila YA resuelta -- un
    ADMIN vinculando SU PROPIA cuenta; el guard de "solo mi propia fila"
    vive en la capa de API, que resuelve `usuario` a partir del actor
    autenticado, nunca de un id arbitrario del request). Un código nuevo
    invalida silenciosamente cualquier código anterior sin consumir, al
    sobrescribir el mismo hash/expiración. Devuelve el código EN CLARO --
    la única vez que existe fuera de la memoria del proceso -- para que la
    API lo muestre una sola vez; nunca se persiste en claro."""
    codigo = _generar_codigo_crudo()
    usuario.codigo_vinculacion_hash = _hashear(codigo)
    usuario.codigo_vinculacion_expira = datetime.now(timezone.utc) + timedelta(
        minutes=_TTL_MINUTOS
    )
    return codigo


async def consumir_codigo_vinculacion(
    db: AsyncSession, codigo: str, telegram_id: int
) -> Usuario:
    """Claim atómico (post-Phase-4 review, finding #2): `UPDATE usuario SET
    telegram_id=:telegram_id, codigo_vinculacion_hash=NULL,
    codigo_vinculacion_expira=NULL WHERE codigo_vinculacion_hash=:hash AND
    codigo_vinculacion_expira > :ahora RETURNING id`. 0 filas afectadas ->
    no hay match, o el que matcheó ya expiró -> `CodigoVinculacionInvalidoError`
    (mismo criterio que `SolicitudYaResuelta`/`CargaYaAnuladaError`: no
    distingue "no existe" de "expiró" en el tipo de excepción -- ver el
    docstring de la excepción -- ambos casos fallan la MISMA claúsula
    atómica). Esto cierra la ventana de carrera entre el chequeo y la
    escritura: dos consumos concurrentes del MISMO código solo pueden
    ganar el claim uno de los dos, el que pierde ve 0 filas afectadas ANTES
    de tocar el `telegram_id` de nadie."""
    hash_presentado = _hashear(codigo)
    ahora = datetime.now(timezone.utc)
    claim = await db.execute(
        update(Usuario)
        .where(
            Usuario.codigo_vinculacion_hash == hash_presentado,
            Usuario.codigo_vinculacion_expira > ahora,
        )
        .values(telegram_id=telegram_id, codigo_vinculacion_hash=None, codigo_vinculacion_expira=None)
        .returning(Usuario.id)
    )
    usuario_id = claim.scalars().first()
    if usuario_id is None:
        raise CodigoVinculacionInvalidoError("Código de vinculación inválido o expirado.")

    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = result.scalars().first()
    if usuario is None:
        raise UsuarioNoEncontradoTrasClaim(
            f"El claim de vinculación afectó una fila (usuario {usuario_id}), "
            "pero no se encontró esa fila al releerla."
        )
    # Sincroniza en memoria lo que el UPDATE ya escribió -- mismo criterio
    # que `resolver_solicitud`/`_reclamar_anulacion` (necesario contra
    # `FakeAsyncSession`, que nunca aplica un `UPDATE` de verdad).
    usuario.telegram_id = telegram_id
    usuario.codigo_vinculacion_hash = None
    usuario.codigo_vinculacion_expira = None
    return usuario
