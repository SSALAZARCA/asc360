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
-- it is not yet wired everywhere. PR1 introduced the module and wired
`assert_prev_codes_free` into `update_catalog_item`'s existing `prev_codes`
PATCH path. PR2 (this PR) wires the Repuestos tab
(`update_spare_part_item`, `PATCH /imports/spare-part-items/{item_id}`)
and the Reconciliación modal (`update_reconciliation_result` /
`_apply_item_fields`, `PATCH /imports/reconciliation-results/{result_id}`)
through `set_description_es` for the linked-`SparePartItem` case, with a
field-level superadmin gate (D8/D9) on `description`/`description_es`
only -- every other field on those endpoints keeps its existing
`_require_imports_editor` permission. A pure EXTRA `ReconciliationResult`
row (`spare_part_item_id IS NULL`) has no catalog identity and keeps its
RR-local write instead (D1/D22) -- it is NOT routed through this module.
Ajuste de Pedidos already routes through the superadmin-only
`/parts/admin/catalog/{fpn}` endpoint directly (verified working as
intended, not this module's concern). The not-yet-cataloged-code
candidate flow lands in PR3; the superadmin-only guarantee elsewhere
applies only where this module is actually called.

This module also owns:
- `assert_prev_codes_free`: the `prev_codes` collision guard reused by
  `update_catalog_item` (D6) -- diff-based, tolerates pre-existing
  collisions already in prod, only rejects newly-added ones.
- `create_reference`: the safe historied-creation pattern lifted from
  `approve_review_task` (D5), reused by the not-yet-cataloged-code flow.
- `resolve_names`: the exact-code batch resolver used by 2 of the 6
  live-read paths (R2/R3, R5); the other 3 (R1, R4, R6) reimplement the same
  filter rule inline instead of calling it, for performance -- see
  `resolve_names`'s own docstring below for the full explanation and the
  keep-in-sync warning.
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
    """Superadmin/administrativo-only gate for editing a part's Spanish
    display name on ANY surface (D8/D9). No carve-out for already-catalogued
    codes -- called unconditionally at the top of every write path (D10)."""
    if not (getattr(current_user, "is_superadmin", False) or getattr(current_user, "is_administrativo", False)):
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "Solo superadmin o administrativo puede editar el nombre del repuesto",
                "code": "NAME_EDIT_FORBIDDEN",
            },
        )


def _normalize_manual_name(value: Optional[str]) -> Optional[str]:
    """Trims `value` and converts an empty/whitespace-only result to `None`
    so `parts_references.description_es_manual` is NEVER persisted as a
    non-`None` whitespace-only string -- it is either real trimmed text or
    SQL `NULL`.

    Why this matters (`sdd/parts-description-source-of-truth` PR5 fix pass
    #9, a CRITICAL finding from a 5th independent review): Postgres
    `COALESCE(description_es_manual, spi_latest.description_es)`
    (`parts_manual.py`'s `_list_catalog_impl`) only falls back when the
    first argument is SQL `NULL` -- NOT when it is `''` or `'   '`. A
    whitespace-only manual value stored verbatim would survive that
    `COALESCE` unchanged, so the catalog would display whitespace instead
    of falling back to the borrowed spi-latest name, and
    `_resolve_catalog_suggestion`'s `is_confirmed` check (which DOES
    correctly treat a whitespace manual as unconfirmed) would then attach
    `has_unconfirmed_suggestion=True` to that garbage whitespace text
    instead of the real suggestion. Normalizing at write time means every
    write path that stores through this module can never introduce that
    state again, regardless of whether the caller (or a future caller)
    remembers to trim client input."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


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

    `value` is normalized via `_normalize_manual_name` before either write
    (PR5 fix pass #9): a trimmed-empty/whitespace-only submission is
    persisted as `NULL`, never as a literal whitespace string, so it can
    never survive `COALESCE(description_es_manual, ...)` on the read side.
    This is the single normalization point every write path funnels
    through -- see that helper's docstring for the full CRITICAL-bug
    rationale.
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

    normalized_value = _normalize_manual_name(value)
    ref.description_es_manual = normalized_value

    codes = [ref.factory_part_number] + _normalize_codes(ref.prev_codes)
    await db.execute(
        sa_update(SparePartItem)
        .where(SparePartItem.part_number.in_(codes))
        .values(description_es=normalized_value)
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

    Reused by the not-yet-cataloged-code creation flow (design D4, wired in
    PR3's `create_code_candidate`). `description_es_manual` is normalized
    (PR5 fix pass #9, see `_normalize_manual_name`) so a whitespace-only
    submission is stored as `NULL` here too, even though `create_code_candidate`
    also immediately re-writes the same field through `set_description_es`
    right after creation whenever it is non-`None` -- this keeps the row
    correct for the brief in-transaction window between the two writes and
    for any future caller that creates a reference without that follow-up
    call."""
    description_es_manual = _normalize_manual_name(description_es_manual)
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
    exact-code only (no alias resolution), returning only non-empty values
    so a caller can safely do `resolved.get(code) or stored_value` and fall
    back cleanly when there's no confirmed catalog name yet -- see
    sdd/parts-description-source-of-truth design D12.

    Called directly by only 2 of the 6 live-read paths this rule feeds:
    `imports.py`'s `search_spare_parts` (R5) and `_fetch_enriched_reconciliation`
    (R2/R3). The other 3 (`list_spare_part_items` / R1, `export_spare_parts`
    / R4 in `imports.py`, and `list_backorders` / R6 in `imports_service.py`)
    do NOT call this function -- each of them already runs a `PartsReference`
    query for an unrelated column (`rotation_class`), so they reimplement
    this exact same "batch-select PartsReference, keep only non-empty names"
    logic inline, fused into that existing query, to avoid a second
    round-trip. R2/R3 and R5 have no such existing query to fuse into, so
    calling this shared function there costs the same one extra round-trip
    either way.

    IMPORTANT: this resolution rule now exists in 4 places (this function
    plus 3 inline reimplementations). If the rule ever changes (e.g. the
    fallback precedence, or which values count as "empty"), all 4 must be
    updated together -- see the "keep in sync" comment at each of the 3
    inline call sites (R1, R4, R6)."""
    codes = list({p for p in part_numbers if p})
    if not codes:
        return {}

    stmt = select(
        PartsReference.factory_part_number, PartsReference.description_es_manual
    ).where(PartsReference.factory_part_number.in_(codes))
    rows = (await db.execute(stmt)).all()
    return {code: name for code, name in rows if name}
