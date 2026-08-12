"""
Shared write path for a part's Spanish display name
(`parts_references.description_es_manual`) -- `sdd/parts-description-source-of-truth`
design D1-D10.

Every surface that edits a part's name (Maestro de Partes, Ajuste de
Pedidos, Repuestos tab, Reconciliación modal) is DESIGNED to delegate to
`set_description_es`, the single write path (D1/D2) that enforces the
superadmin-only gate (D8/D9/D10) unconditionally, before any lookup or
mutation, whenever it is called.

This is the shared contract the rest of the change (PR2-5) routes through
-- it is not yet wired everywhere. PR1 (this PR) only introduces the
module and wires `assert_prev_codes_free` into `update_catalog_item`'s
existing `prev_codes` PATCH path. Ajuste de Pedidos, the Repuestos tab and
the Reconciliación modal are not yet routed through `set_description_es`;
that wiring lands in PR2-5 per the design's phased rollout. Until then,
the superadmin-only guarantee applies only where this module is actually
called, not across the whole application.

This module also owns:
- `assert_prev_codes_free`: the `prev_codes` collision guard reused by
  `update_catalog_item` (D6) -- diff-based, tolerates pre-existing
  collisions already in prod, only rejects newly-added ones.
- `create_reference`: the safe historied-creation pattern lifted from
  `approve_review_task` (D5), reused by the not-yet-cataloged-code flow.
- `resolve_names`: the exact-code batch resolver consumed by the live-read
  conversion of the 6 read paths (R1-R6, D11-D14).
"""
import logging
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.imports import SparePartItem
from app.models.parts_manual import PartsReference
from app.services.pricing_service import _find_reference_for_part_number

logger = logging.getLogger(__name__)

# Max number of historical aliases kept in `PartsReference.prev_codes`.
# Shared with `app/api/v1/parts_manual.py`'s `update_catalog_item` truncation
# of the submitted list -- both must agree on the same cap.
MAX_PREV_CODES = 5


def assert_name_editor(current_user) -> None:
    """Superadmin-only gate for editing a part's Spanish display name on ANY
    surface (D8/D9). No carve-out for already-catalogued codes -- called
    unconditionally at the top of every write path (D10)."""
    if not getattr(current_user, "is_superadmin", False):
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "Solo superadmin puede editar el nombre del repuesto",
                "code": "NAME_EDIT_FORBIDDEN",
            },
        )


def _normalize_codes(entries) -> list[str]:
    """Tolerates both the new dict format (`{"code": "..."}`) and the legacy
    plain-string format stored in `prev_codes`."""
    codes: list[str] = []
    for entry in entries or []:
        if isinstance(entry, dict) and entry.get("code"):
            codes.append(entry["code"])
        elif isinstance(entry, str) and entry:
            codes.append(entry)
    return codes


async def set_description_es(
    db: AsyncSession,
    *,
    part_number: str,
    value: str,
    model_applicable: Optional[str],
    current_user,
) -> PartsReference:
    """Writes `description_es_manual` on the canonical `PartsReference` AND
    fans out a mirror write to `spare_part_items.description_es` for every
    code in `[factory_part_number] + prev_codes` -- the single write path
    for a part's Spanish name (D1/D2). Resolves `part_number` through the
    alias-aware lookup (D3) first; the mirror write is data hygiene only,
    FOB-inert (touches only `description_es`) (D2/D13).

    `model_applicable` is accepted for interface parity with the
    not-yet-cataloged-code flow (design D4, wired in a later PR) but is
    unused by this write path in PR1.
    """
    assert_name_editor(current_user)

    ref = await _find_reference_for_part_number(db, part_number)
    if not ref:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "El código no está en el catálogo",
                "code": "PART_NOT_IN_CATALOG",
            },
        )

    ref.description_es_manual = value

    codes = [ref.factory_part_number] + _normalize_codes(ref.prev_codes)
    await db.execute(
        sa_update(SparePartItem)
        .where(SparePartItem.part_number.in_(codes))
        .values(description_es=value)
    )

    return ref


async def assert_prev_codes_free(
    db: AsyncSession,
    *,
    factory_part_number: str,
    submitted: Iterable[str],
    existing: Iterable,
) -> None:
    """`prev_codes` collision guard (D6). Only codes newly added relative to
    `existing` are validated against live `PartsReference` primary keys
    elsewhere -- pre-existing colliding aliases already in prod are
    tolerated so old corruption never permanently 409s an unrelated edit.

    Uses a locking read (`SELECT ... FOR UPDATE`, the same pessimistic-lock
    idiom used in `remisiones.py`'s `despachar` endpoint) instead of a plain
    `db.get`. This closes the race against a concurrent request that
    modifies or deletes an ALREADY-EXISTING colliding `PartsReference` while
    this check is in flight -- that request now blocks on the row instead of
    racing past it undetected. It does NOT close the narrower phantom-insert
    case where the colliding code doesn't exist yet at check time and a
    concurrent request creates it in the same window; closing that would
    require a DB-level constraint or serializable isolation, not just a row
    lock, and is out of scope for this guard.
    """
    submitted_codes = set(_normalize_codes(list(submitted)))
    existing_codes = set(_normalize_codes(list(existing)))
    # Sorted so the reported collision (and the order rows are locked/read)
    # is deterministic across runs, not dependent on Python's set hash order.
    newly_added = sorted(submitted_codes - existing_codes)

    for code in newly_added:
        stmt = (
            select(PartsReference)
            .where(PartsReference.factory_part_number == code)
            .with_for_update()
        )
        conflict = (await db.execute(stmt)).scalar_one_or_none()
        if conflict is not None and conflict.factory_part_number != factory_part_number:
            logger.warning(
                "prev_codes collision rejected: colliding_code=%s editing_reference=%s",
                code, factory_part_number,
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "detail": (
                        f"El código '{code}' ya existe en el catálogo como referencia "
                        "independiente. Usá el flujo de revisión para fusionarlas."
                    ),
                    "code": "PREV_CODE_COLLISION",
                },
            )


async def create_reference(
    db: AsyncSession,
    *,
    factory_part_number: str,
    description: str,
    description_es_manual: Optional[str],
    source_ref: Optional[PartsReference] = None,
) -> PartsReference:
    """Safe historied-creation pattern lifted from `approve_review_task`
    (D5). When `source_ref` is given (a matched candidate), the new row
    inherits `um_part_number`/`unit`/`rotation_class` and gains a
    `prev_codes` history entry pointing back at it -- the same shape
    `approve_review_task` already builds. When `source_ref` is `None` (no
    candidate found), a fresh orphan `PartsReference` is created instead.

    Not wired to any live endpoint yet -- intentionally unreferenced until
    PR3 wires the not-yet-cataloged-code creation flow (design D4)."""
    if source_ref is not None:
        new_prev = ([{"code": source_ref.factory_part_number}] + list(source_ref.prev_codes or []))[:MAX_PREV_CODES]
        new_ref = PartsReference(
            factory_part_number=factory_part_number,
            um_part_number=source_ref.um_part_number,
            description=description or source_ref.description,
            description_es_manual=(
                description_es_manual if description_es_manual is not None
                else source_ref.description_es_manual
            ),
            unit=source_ref.unit,
            prev_codes=new_prev,
            rotation_class=source_ref.rotation_class,
        )
    else:
        new_ref = PartsReference(
            factory_part_number=factory_part_number,
            um_part_number=factory_part_number,
            description=description,
            description_es_manual=description_es_manual,
            prev_codes=[],
        )

    db.add(new_ref)
    await db.flush()
    return new_ref


async def resolve_names(db: AsyncSession, part_numbers: Iterable[str]) -> dict[str, str]:
    """Batch-resolves `description_es_manual` for a set of `part_number`s,
    exact-code only (no alias resolution -- D12), returning only non-empty
    values. Consumed by the live-read conversion of R1-R6.

    Not wired to any live endpoint yet -- intentionally unreferenced until
    PR4 wires the live-read conversion (R1-R6, design D11-D14)."""
    codes = list({p for p in part_numbers if p})
    if not codes:
        return {}

    stmt = select(
        PartsReference.factory_part_number, PartsReference.description_es_manual
    ).where(PartsReference.factory_part_number.in_(codes))
    rows = (await db.execute(stmt)).all()
    return {code: name for code, name in rows if name}
