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

Phase 2 (this batch): the route guards the caller (403 non-superadmin, 401
no token — via the same `get_current_user` dependency the frontend's
`authFetch` feeds), then delegates the whole transactional creation to
`app.services.historical_order_service.create_historical_order`. That
service already raises the correctly-mapped `HTTPException` for every
failure mode (409 duplicate warning, 422 status/date mismatch, 409/500
sanitized errors) — this route has nothing left to translate.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser
from app.api.v1.superadmin_data import _require_superadmin
from app.schemas.historical_order import HistoricalOrderCreate, HistoricalOrderOut
from app.services.historical_order_service import create_historical_order

router = APIRouter(prefix="/superadmin/data", tags=["superadmin_historical_orders"])


@router.post("/historical-orders", response_model=HistoricalOrderOut, status_code=201)
async def create_historical_order_endpoint(
    payload: HistoricalOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)
    return await create_historical_order(db, payload, current_user)
