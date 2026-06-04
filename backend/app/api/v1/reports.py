"""
Reports API — Informe Gerencial PDF endpoint.

GET /reports/gerencial?desde=YYYY-MM-DD&hasta=YYYY-MM-DD
- Superadmin only
- Returns application/pdf inline (StreamingResponse)
"""
import io
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, CurrentUser
from app.database import get_db
from app.services.report_service import generate_gerencial_report

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/gerencial")
async def get_gerencial_report(
    desde: date = Query(..., description="Start date (YYYY-MM-DD)"),
    hasta: date = Query(..., description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Generate and download the management PDF report for the given date range.
    Superadmin access required.
    """
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin puede generar este informe")

    if desde > hasta:
        raise HTTPException(
            status_code=422,
            detail="desde must be before or equal to hasta",
        )

    try:
        pdf_bytes = await generate_gerencial_report(desde, hasta, db)
    except Exception as exc:
        logger.error("Error generating gerencial report: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Error generando el informe") from exc

    filename = f"informe-gerencial-{desde}_{hasta}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
