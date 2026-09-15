"""
Motored Pedidos — rastro de auditoría de EDICIÓN DE MAESTROS
(sdd/motored-pedidos-cimientos, Fase 3, task 3.6, §7.15).

Alcance cerrado en la proposal: auditoría de MAESTROS únicamente (sucursal,
bodega, proveedor, referencia), no un sistema de auditoría general. Cada
llamada agrega una fila a la sesión vía `db.add(...)` -- el commit es
responsabilidad del caller (ADR-5, sin auto-commit).
"""
import uuid
from typing import Any, Dict, List, Optional

from app.motored.models.auditoria_maestro import AuditoriaMaestro


def _stringify(value: Any) -> Optional[str]:
    return None if value is None else str(value)


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
