"""`confirmar` writes the shared state with ONE atomic upsert, so two asesores
answering the same brand-new invoice at once cannot fail on the unique key."""
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql

from app.motored.models.factura_confirmacion_ingreso import (
    FacturaConfirmacionIngreso,
    FacturaConfirmacionIngresoHistorial,
)
from app.motored.services import ingresos_pendientes as ip
from app.motored.services import sucursal_grupo

TIENDA = uuid.uuid4()


async def test_confirm_upserts_the_state_on_the_unique_key(monkeypatch):
    item = {"prefijo_rh": "RH", "numero_rh": 5, "factura": "RH 5",
            "sucursal_id": TIENDA, "fecha": date(2026, 10, 1), "dias": 7}
    monkeypatch.setattr(sucursal_grupo, "principal_de", AsyncMock(return_value={}))
    monkeypatch.setattr(ip, "pendientes", AsyncMock(return_value=[item]))
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    out = await ip.confirmar(db, "RH 5", TIENDA, "LLEGO", ip.Actor(nombre="Ana"), "link")

    assert out["estado"] == "LLEGO" and out["confirmado_por"] == "Ana"
    [(stmt,), _] = db.execute.await_args
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert sql.startswith("INSERT INTO factura_confirmacion_ingreso")
    assert "ON CONFLICT (prefijo_rh, numero_rh, sucursal_id) DO UPDATE" in sql
    # No ORM insert of the state (that is what raced); only the history row.
    agregados = [type(c.args[0]) for c in db.add.call_args_list]
    assert agregados == [FacturaConfirmacionIngresoHistorial]
    assert FacturaConfirmacionIngreso not in agregados
    db.commit.assert_awaited_once()
