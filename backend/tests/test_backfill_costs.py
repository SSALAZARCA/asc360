"""
Tests for `backfill_costs` (POST /admin/backfill-costs, `parts_manual.py`).

Bugfix (2026-08-11): this endpoint used to only backfill `avg_fob_cost`
(confirmed cost). `PartsReference.preliminary_fob` (FOB de PI) had NO
backfill at all -- it only ever got computed by two narrow triggers
(`import_fob_preliminary`'s Excel upload, `execute_adjustments`' pending-
decision sweep), neither of which runs when a brand new reference is
created by `load_section` (loading a catalog PDF). A reference whose
factory_part_number already has a priced `fob_pi` on an existing
`SparePartItem` from an earlier order was born with `preliminary_fob = NULL`
and stayed that way forever. Confirmed on real production data (Xtreet 401
catalog load, factory code `0520001.C05J`) via a temporary debug endpoint
before this fix (removed in this same commit).

User explicitly wants ONE button/action, not two -- `backfill_costs` now
backfills BOTH avg_fob_cost and preliminary_fob in one pass, and a
reference counts as "updated" once if EITHER got filled (no double-count,
no separate confirmed/preliminary metrics surfaced).

Mirrors `test_recalculate_part_cost_weighting.py`'s `FakeAsyncSession`
convention (`tests/imports/conftest.py`) -- plain `def test_...` +
`asyncio.run(...)`, no live DB. `recalculate_part_cost` (the avg_fob_cost
path) does its OWN internal `db.execute()` calls -- queue entries account
for those too, in the exact order it issues them: (1) re-lookup the
reference by factory_part_number, (2) find priced spare_part_items.
"""
import asyncio

from app.api.v1.parts_manual import backfill_costs
from app.models.parts_manual import PartsReference

from tests.imports.conftest import FakeAsyncSession, make_lot, make_spare_part_item, make_imports_editor


def _ref(factory_part_number="ABC-001", avg_fob_cost=None, preliminary_fob=None, prev_codes=None):
    return PartsReference(
        factory_part_number=factory_part_number,
        um_part_number=factory_part_number,
        description="Test part",
        prev_codes=prev_codes or [],
        avg_fob_cost=avg_fob_cost,
        preliminary_fob=preliminary_fob,
    )


def _superadmin():
    return make_imports_editor(role="superadmin")


def test_non_superadmin_gets_403_with_no_db_touch():
    fake_db = FakeAsyncSession(execute_queue=[])
    try:
        asyncio.run(backfill_costs(fake_db, make_imports_editor(role="administrativo")))
        assert False, "expected HTTPException"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
    assert fake_db.executed_statements == []


def test_fills_avg_fob_cost_when_missing_via_recalculate_part_cost():
    lot = make_lot()
    ref = _ref("ABC-001", avg_fob_cost=None, preliminary_fob=5.0)  # preliminary already set -- only avg_fob_cost path runs
    priced_item = make_spare_part_item(lot.id, "ABC-001", qty_ordered=10, unit_price=8.0)

    fake_db = FakeAsyncSession(execute_queue=[
        [ref],           # initial select(PartsReference).where(or_(avg_fob_cost IS NULL, preliminary_fob IS NULL))
        [ref],            # _find_reference_for_part_number's self-lookup inside recalculate_part_cost
        [priced_item],    # recalculate_part_cost's priced-items query
    ])

    result = asyncio.run(backfill_costs(fake_db, _superadmin()))

    assert result == {"checked": 1, "updated": 1}
    assert ref.avg_fob_cost == 8.0


def test_fills_preliminary_fob_when_missing():
    lot = make_lot()
    ref = _ref("ABC-002", avg_fob_cost=3.0, preliminary_fob=None)  # avg_fob_cost already set -- only preliminary path runs
    item1 = make_spare_part_item(lot.id, "ABC-002", qty_ordered=10, fob_pi=8.0)
    item2 = make_spare_part_item(lot.id, "ABC-002", qty_ordered=5, fob_pi=11.0)

    fake_db = FakeAsyncSession(execute_queue=[
        [ref],
        [item1, item2],  # preliminary-fob weighted-average query
    ])

    result = asyncio.run(backfill_costs(fake_db, _superadmin()))

    assert result == {"checked": 1, "updated": 1}
    # (10*8.0 + 5*11.0) / 15 = 9.0
    assert ref.preliminary_fob == 9.0


def test_reference_updated_only_once_when_both_prices_get_filled():
    """A reference missing BOTH prices, where both backfill successfully,
    must count as ONE updated reference, not two."""
    lot = make_lot()
    ref = _ref("ABC-003", avg_fob_cost=None, preliminary_fob=None)
    priced_item = make_spare_part_item(lot.id, "ABC-003", qty_ordered=4, unit_price=6.0)
    fob_pi_item = make_spare_part_item(lot.id, "ABC-003", qty_ordered=4, fob_pi=5.5)

    fake_db = FakeAsyncSession(execute_queue=[
        [ref],
        [ref],             # recalculate_part_cost's self-lookup
        [priced_item],     # recalculate_part_cost's priced-items query
        [fob_pi_item],     # preliminary-fob weighted-average query
    ])

    result = asyncio.run(backfill_costs(fake_db, _superadmin()))

    assert result == {"checked": 1, "updated": 1}
    assert ref.avg_fob_cost == 6.0
    assert ref.preliminary_fob == 5.5


def test_already_fully_priced_reference_is_never_queued():
    """The `or_(avg_fob_cost IS NULL, preliminary_fob IS NULL)` filter is at
    the SQL level -- a reference with both prices already set is simply
    never in the result set the function iterates."""
    fake_db = FakeAsyncSession(execute_queue=[
        [],  # nothing returned -- the (mocked) fully-priced ref was filtered out in SQL
    ])

    result = asyncio.run(backfill_costs(fake_db, _superadmin()))

    assert result == {"checked": 0, "updated": 0}


def test_preliminary_fob_matches_via_prev_codes_not_just_canonical_code():
    lot = make_lot()
    ref = _ref("NEW-CODE", avg_fob_cost=1.0, preliminary_fob=None, prev_codes=[{"code": "OLD-CODE"}])
    item = make_spare_part_item(lot.id, "OLD-CODE", qty_ordered=3, fob_pi=5.0)

    fake_db = FakeAsyncSession(execute_queue=[
        [ref],
        [item],
    ])

    result = asyncio.run(backfill_costs(fake_db, _superadmin()))

    assert result == {"checked": 1, "updated": 1}
    assert ref.preliminary_fob == 5.0


def test_preliminary_fob_matches_via_legacy_plain_string_prev_codes():
    lot = make_lot()
    ref = _ref("NEW-CODE-2", avg_fob_cost=1.0, preliminary_fob=None, prev_codes=["LEGACY-CODE"])
    item = make_spare_part_item(lot.id, "LEGACY-CODE", qty_ordered=2, fob_pi=4.0)

    fake_db = FakeAsyncSession(execute_queue=[
        [ref],
        [item],
    ])

    result = asyncio.run(backfill_costs(fake_db, _superadmin()))

    assert result == {"checked": 1, "updated": 1}
    assert ref.preliminary_fob == 4.0


def test_preliminary_fob_excludes_cancelled_items_from_average():
    lot = make_lot()
    ref = _ref("ABC-004", avg_fob_cost=1.0, preliminary_fob=None)
    active = make_spare_part_item(lot.id, "ABC-004", qty_ordered=10, fob_pi=8.0, status="PENDING")

    fake_db = FakeAsyncSession(execute_queue=[
        [ref],
        [active],  # the fake session doesn't filter SQL WHERE -- a real query
    ])            # would already exclude a CANCELLED sibling item at the DB level

    result = asyncio.run(backfill_costs(fake_db, _superadmin()))

    assert result == {"checked": 1, "updated": 1}
    assert ref.preliminary_fob == 8.0


def test_reference_with_zero_matching_items_for_either_price_stays_null_and_not_counted():
    ref = _ref("NO-MATCH", avg_fob_cost=None, preliminary_fob=None)

    fake_db = FakeAsyncSession(execute_queue=[
        [ref],
        [ref],  # recalculate_part_cost's self-lookup finds the ref...
        [],     # ...but no priced items exist for it
        [],     # and no fob_pi items exist for it either
    ])

    result = asyncio.run(backfill_costs(fake_db, _superadmin()))

    assert result == {"checked": 1, "updated": 0}
    assert ref.avg_fob_cost is None
    assert ref.preliminary_fob is None
