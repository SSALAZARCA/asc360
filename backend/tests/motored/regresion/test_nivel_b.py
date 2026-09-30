"""
Motored Pedidos F3 "Motor" (S8b-3, ADR-10, spec Domain 4 nivel B) — pipeline
contra el libro REAL y una base de pruebas ya cargada (opt-in).

Corre sólo con todas estas variables (sin ellas se omite, no falla):

- `MOTORED_REGRESION_EXCEL`: libro de referencia (fuera del repositorio);
- `MOTORED_REGRESION_DB_URL`: base de pruebas `postgresql+asyncpg://...`
  migrada y cargada con los archivos REVISADOS por la ingesta real de F2;
- `MOTORED_REGRESION_SUCURSAL_ID`: UUID de la sucursal del libro;
- `MOTORED_REGRESION_CORTE` (AAAA-MM-DD) para crear la corrida base, o
  `MOTORED_REGRESION_CORRIDA_ID` si ya existe;
- `MOTORED_REGRESION_ACEPTACIONES` (opcional): `{código: categoría}`.

Compara primero las entradas (E:J, T, U, V, W, X) y después las salidas con
las reglas del A2. La base es de pruebas: la corrida base queda en ella.
"""
import os
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest

from app.motored.herramientas.regresion.corrida_db import leer_nivel_b
from app.motored.herramientas.regresion.delta_db import (
    crear_y_calcular,
    sesion_desde_url,
)
from app.motored.herramientas.regresion.extractor_excel import leer_libro
from app.motored.herramientas.regresion.nivel_b import (
    ejecutar_nivel_b,
    resumen_texto_b,
)
from app.motored.herramientas.regresion.rutas import (
    ENV_ACEPTACIONES,
    ENV_DB_URL,
    ENV_EXCEL,
)
from app.motored.herramientas.regresion.taxonomia import (
    SIN_CATEGORIA,
    cargar_aceptaciones,
)

ENV_SUCURSAL_ID = "MOTORED_REGRESION_SUCURSAL_ID"
ENV_CORTE = "MOTORED_REGRESION_CORTE"
ENV_CORRIDA_ID = "MOTORED_REGRESION_CORRIDA_ID"

RUTA = os.environ.get(ENV_EXCEL)
URL = os.environ.get(ENV_DB_URL)
SUCURSAL = os.environ.get(ENV_SUCURSAL_ID)
CORTE = os.environ.get(ENV_CORTE)
CORRIDA = os.environ.get(ENV_CORRIDA_ID)
pytestmark = [
    pytest.mark.regresion,
    pytest.mark.skipif(
        not (RUTA and URL and SUCURSAL and (CORTE or CORRIDA)),
        reason=(
            f"{ENV_EXCEL}, {ENV_DB_URL}, {ENV_SUCURSAL_ID} y "
            f"{ENV_CORTE} o {ENV_CORRIDA_ID} no definidas"
        ),
    ),
]


def _aceptaciones():
    ruta = os.environ.get(ENV_ACEPTACIONES)
    return cargar_aceptaciones(Path(ruta)) if ruta else {}


async def test_las_entradas_y_luego_las_salidas_se_explican_todas():
    lectura = leer_libro(Path(RUTA))
    sucursal_id = UUID(SUCURSAL)
    async with sesion_desde_url(URL) as db:
        corrida_id = UUID(CORRIDA) if CORRIDA else await crear_y_calcular(
            db, date.fromisoformat(CORTE), sucursal_id
        )
        leida = await leer_nivel_b(db, corrida_id, sucursal_id)

    resultado = ejecutar_nivel_b(
        lectura, leida.app, _aceptaciones(), leida.reproduccion_identica
    )

    informe = "\n".join(resumen_texto_b(resultado))
    assert leida.reproduccion_identica, informe
    sin_explicar = [
        d for d in resultado.entradas if d.categoria == SIN_CATEGORIA
    ]
    assert sin_explicar == [], informe
    assert resultado.paso, informe
