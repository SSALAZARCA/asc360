"""
Historical Order Entry — superadmin-only creation of a complete, backdated
service order (vehicle, client, dates, status, diagnosis, lifecycle events,
PDF, audit log) for paper orders written when Sonia was unavailable.

Separate module from `app/api/v1/superadmin_data.py` on purpose (Decision 1
of the design): that file already documents 5 phases of a different
capability (quick-fix corrections, not creation). Same `/superadmin/data`
URL prefix, separate module — no further growth of an already-large file.

Imports `_require_superadmin` from `superadmin_data` (Decision 2) instead of
duplicating the guard, so both modules share one source of truth for the
exact 403 envelope. This is a read-only import — `superadmin_data.py` is
never modified by this change.

Phase 1 (this batch): router skeleton only. The route guards the caller
(403 non-superadmin, 401 no token — via the same `get_current_user`
dependency the frontend's `authFetch` feeds) and returns 501 Not
Implemented. The real transactional service
(`app.services.historical_order_service.create_historical_order`) is wired
in here in the next PR, replacing the `NotImplementedError` below.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser
from app.api.v1.superadmin_data import _require_superadmin
from app.schemas.historical_order import HistoricalOrderCreate

router = APIRouter(prefix="/superadmin/data", tags=["superadmin_historical_orders"])


@router.post("/historical-orders", status_code=201)
async def create_historical_order_endpoint(
    payload: HistoricalOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Stub for Phase 1 — guard only, zero DB reads/writes. Deliberately
    raises 501 so the frontend (shipped in a later PR) can distinguish
    "not authorized" from "not built yet" while this PR is deployed alone."""
    _require_superadmin(current_user)
    raise HTTPException(status_code=501, detail="Historical order creation not implemented yet")
