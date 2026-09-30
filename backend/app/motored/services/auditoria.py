"""
Motored Pedidos — rastro de auditoría de EDICIÓN DE MAESTROS
(sdd/motored-pedidos-cimientos, Fase 3, task 3.6, §7.15).

Alcance cerrado en la proposal: auditoría de MAESTROS únicamente (sucursal,
bodega, proveedor, referencia), no un sistema de auditoría general. Cada
llamada agrega una fila a la sesión vía `db.add(...)` -- el commit es
responsabilidad del caller (ADR-5, sin auto-commit).
"""
import hashlib
import uuid
from typing import Any, Dict, List, Optional

from app.motored.models.auditoria_maestro import AuditoriaMaestro


_VALOR_MAX_LENGTH = 500  # matches `AuditoriaMaestro.valor_anterior/valor_nuevo` String(500)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _clip_items(items: List[str], full_text: str) -> str:
    """Keeps whole items only (never cuts one in half) and appends a marker
    with how many were left out plus a short hash of the FULL value, so two
    different long values never collapse into the same audit text."""
    shown: List[str] = []
    for item in items:
        candidate = ", ".join([*shown, item])
        marker = f" … (+{len(items) - len(shown) - 1} más, #{_digest(full_text)})"
        if len(candidate) + len(marker) > _VALOR_MAX_LENGTH:
            break
        shown.append(item)
    marker = f" … (+{len(items) - len(shown)} más, #{_digest(full_text)})"
    return ", ".join(shown) + marker


def _stringify(value: Any) -> Optional[str]:
    """List values (e.g. `referencia.homologados`) are joined readably.
    Anything longer than the column is clipped by `_clip_items` (lists) or
    to a prefix + hash marker (scalars), so the commit never fails and a real
    change is never hidden by the clipping."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        items = [str(v) for v in value]
        text = ", ".join(items)
        return text if len(text) <= _VALOR_MAX_LENGTH else _clip_items(items, text)
    text = str(value)
    if len(text) <= _VALOR_MAX_LENGTH:
        return text
    marker = f" … (#{_digest(text)})"
    return text[: _VALOR_MAX_LENGTH - len(marker)] + marker


def _record(
    db,
    entidad: str,
    entidad_id: uuid.UUID,
    usuario_id: Optional[uuid.UUID],
    accion: str,
    campo: Optional[str] = None,
    valor_anterior: Any = None,
    valor_nuevo: Any = None,
) -> AuditoriaMaestro:
    row = AuditoriaMaestro(
        entidad=entidad,
        entidad_id=entidad_id,
        usuario_id=usuario_id,
        accion=accion,
        campo=campo,
        valor_anterior=_stringify(valor_anterior),
        valor_nuevo=_stringify(valor_nuevo),
    )
    db.add(row)
    return row


def audit_create(db, entidad: str, entidad_id: uuid.UUID, usuario_id: Optional[uuid.UUID] = None) -> AuditoriaMaestro:
    return _record(db, entidad, entidad_id, usuario_id, accion="create")


def audit_deactivate(db, entidad: str, entidad_id: uuid.UUID, usuario_id: Optional[uuid.UUID] = None) -> AuditoriaMaestro:
    return _record(
        db, entidad, entidad_id, usuario_id, accion="deactivate",
        campo="activa", valor_anterior=True, valor_nuevo=False,
    )


def audit_reactivate(db, entidad: str, entidad_id: uuid.UUID, usuario_id: Optional[uuid.UUID] = None) -> AuditoriaMaestro:
    return _record(
        db, entidad, entidad_id, usuario_id, accion="reactivate",
        campo="activa", valor_anterior=False, valor_nuevo=True,
    )


def audit_password_reset(db, entidad: str, entidad_id: uuid.UUID, usuario_id: Optional[uuid.UUID] = None) -> AuditoriaMaestro:
    """Registra QUE la contraseña cambió, nunca su valor ni su hash."""
    return _record(db, entidad, entidad_id, usuario_id, accion="update", campo="password")


def audit_desbloqueo(db, entidad: str, entidad_id: uuid.UUID, usuario_id: Optional[uuid.UUID] = None) -> AuditoriaMaestro:
    """Registra QUE un ADMIN levantó el bloqueo por intentos fallidos."""
    return _record(db, entidad, entidad_id, usuario_id, accion="update", campo="bloqueado_hasta", valor_nuevo=None)


def diff_and_audit(
    db,
    entidad: str,
    entidad_id: uuid.UUID,
    usuario_id: Optional[uuid.UUID],
    before: Dict[str, Any],
    after: Dict[str, Any],
) -> List[AuditoriaMaestro]:
    """Compara los campos de `before`/`after` y escribe UNA fila de
    auditoría por cada campo que efectivamente cambió. Campos ausentes en
    `after` (es decir, no enviados en la actualización) no generan fila."""
    rows: List[AuditoriaMaestro] = []
    for campo, nuevo in after.items():
        anterior = before.get(campo)
        if anterior != nuevo:
            rows.append(
                _record(db, entidad, entidad_id, usuario_id, accion="update", campo=campo, valor_anterior=anterior, valor_nuevo=nuevo)
            )
    return rows
