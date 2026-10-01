"""
Motored Pedidos F4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2, ADR-3):
esquemas de la edición de líneas y su historial.

`pedido_final` entra SIN tipo (`Any`): la regla de E-CORRIDA-053 la aplica el
servicio, DESPUÉS de los chequeos de estado (404, 042, 065, 052), así un valor
inválido siempre responde con su código y no con el 422 genérico del
validador. Los campos extra se prohíben (no se acepta Z ni nada más).
"""
import datetime
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict

from app.motored.schemas.corrida import LineaRead


class LineaEditar(BaseModel):
    """Cuerpo de `PATCH /corridas/{id}/lineas/{linea_id}`. `esperado` es la
    cantidad que la pantalla vio: si cambió mientras tanto, E-CORRIDA-066."""

    model_config = ConfigDict(extra="forbid")

    pedido_final: Any = None
    esperado: Optional[Decimal] = None


class TotalesTienda(BaseModel):
    """Lo que se va a pedir en la tienda junto al sugerido del motor."""

    unidades_a_pedir: Decimal
    valor_a_pedir: Decimal
    unidades_sugerido: Decimal
    valor_sugerido: Decimal


class LineaEditada(BaseModel):
    """Respuesta del PATCH: la línea ya refrescada y los totales."""

    linea: LineaRead
    totales_tienda: TotalesTienda


class HistorialLinea(BaseModel):
    """Una fila inmutable del historial de una línea."""

    id: int
    linea_id: int
    campo: str
    valor_anterior: Decimal
    valor_nuevo: Decimal
    motivo: str
    detalle: Optional[Dict[str, Any]] = None
    usuario_id: uuid.UUID
    usuario: str
    creado_en: datetime.datetime
