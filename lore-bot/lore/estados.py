"""Conversation state-machine scaffolding for Lore's handlers (Phase 9-12).

No handler/conversation logic lives here yet — this module only defines the
state vocabulary and the shape of an in-progress registration's draft, per
design D7. Written independently for `lore`; not derived from
`telegram-bot/bot/core/constants.py`'s own `ConversationHandler` states.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import IntEnum, auto
from typing import Optional
from uuid import UUID, uuid4


class RegistroEstado(IntEnum):
    """Self-registration flow (`/start` for an unrecognized `telegram_id`)."""

    NOMBRE = auto()
    CELULAR = auto()
    SUCURSAL = auto()
    CONFIRMAR = auto()


class CapturaEstado(IntEnum):
    """Lost-sale capture flow (manual entry, Method A, or photo, Method B)."""

    SUCURSAL = auto()
    METODO = auto()
    MANUAL = auto()
    FOTO = auto()
    SELECCION = auto()
    NO_RESUELTAS = auto()
    CANTIDAD = auto()
    CONFIRMAR = auto()


class CorreccionEstado(IntEnum):
    """Today-only edit/cancel flow for a previously captured registration."""

    LISTA = auto()
    ACCION = auto()
    CANTIDAD = auto()
    CONFIRMAR_ANULAR = auto()


@dataclass
class LineaBorrador:
    """One reference line within an in-progress capture."""

    referencia_id: UUID
    codigo: str
    nombre: Optional[str] = None
    cantidad: Optional[int] = None  # None until the advisor enters a quantity
    # Phase 10 addition: spec's "Explicit toggle selection before
    # confirmation" requirement applies to BOTH manual and photo entry
    # (design D7 — CAP_SELECCION is shared "from CAP_SELECCION onward"), so
    # every candidate line — however it was added — starts unselected until
    # the advisor explicitly toggles it ON.
    seleccionada: bool = False


@dataclass
class Borrador:
    """The draft held in `context.user_data["borrador"]` while capturing.

    `registro_id` is generated once, at `Borrador()` construction time (i.e.
    when `captura.iniciar` starts a new draft) — well before the confirm
    screen — and is never regenerated afterward. It doubles as the
    `Idempotency-Key` sent to `POST /demanda-perdida` (design D5/D7), so a
    retry against the SAME draft (e.g. after a `BackendCaido` on confirm)
    reuses this same value.
    """

    registro_id: UUID = field(default_factory=uuid4)
    sucursal_id: Optional[UUID] = None
    metodo: Optional[str] = None  # "MANUAL" | "FOTO"
    fecha: Optional[date] = None
    lineas: list[LineaBorrador] = field(default_factory=list)
    no_resueltas: list[str] = field(default_factory=list)
