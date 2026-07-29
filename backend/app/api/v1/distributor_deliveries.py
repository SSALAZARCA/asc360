"""
Distributor Vehicle Delivery — `parts_dealer` (Distribuidor) or superadmin
registration of a new motorcycle sale/delivery: a client `User` and a
`Vehicle` created (or reused) in one transaction, with an authoritative
warranty-start date (`Vehicle.delivery_date`) and a role-conditional signed
delivery-act photo (Design ADR 17/18 — mandatory for Distribuidor, optional
for superadmin's legacy-vehicle backfill).

Phase 3 (this batch): router skeleton only. The route guards the caller
(`require_distribuidor` — 403 for any role other than `parts_dealer`/
superadmin, 401 no token — via the same `get_current_user` dependency the
frontend's `authFetch` feeds) and returns 501 Not Implemented. The real
transactional service (`app.services.distributor_delivery_service.
create_delivery`) is wired in here in PR4, replacing the
`HTTPException(501, ...)` below. Mirrors `app/api/v1/
superadmin_historical_orders.py`'s PR1 shape.

`require_distribuidor` is a PUBLIC function name (not `_require_...`) on
purpose — the design's future parts-sale router reuses it verbatim, the
same precedent `_require_superadmin` already set for every
superadmin-only router in this codebase.

The endpoint is multipart from the start (`payload: str = Form(...)` +
`photo: UploadFile | None = File(None)`), per Design ADR 18 — the
role-conditional photo requirement must be checked atomically, in the SAME
request that decides whether to write, so the photo has to be assessable
before any DB write happens. Parsing `payload` and enforcing the photo
requirement are PR4 concerns; this stub 501s before either.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser

router = APIRouter(prefix="/distributor", tags=["distributor_deliveries"])


def require_distribuidor(current_user: CurrentUser) -> None:
    if not (current_user.is_distribuidor or current_user.is_superadmin):
        raise HTTPException(status_code=403, detail="Solo Distribuidor o superadmin")


@router.post("/deliveries", status_code=201)
async def create_delivery_endpoint(
    payload: str = Form(...),
    photo: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Stub for Phase 3 — guard only, zero DB reads/writes. Deliberately
    raises 501 so a caller with valid access can distinguish "not
    authorized" from "not built yet" while this PR is deployed alone."""
    require_distribuidor(current_user)
    raise HTTPException(status_code=501, detail="Distributor delivery creation not implemented yet")
