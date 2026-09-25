"""
Motored Pedidos — router agregador (sdd/motored-pedidos-cimientos, Fase 4).

Monta los 6 sub-routers bajo un único `APIRouter` que `main.py` incluye con
el prefijo final `/api/motored` (ADR-4 / design doc's File Changes table --
NO usa `/api/v1`, ese prefijo es exclusivo de asc360).

ORDEN DE INCLUSIÓN IMPORTANTE: `salud` se registra ANTES que `maestros`
porque ambos exponen una ruta `GET` con el MISMO número de segmentos bajo
`/maestros/...` (`/maestros/salud` vs. el genérico `/maestros/{entidad}`).
Starlette resuelve por el PRIMER router registrado cuyo patrón matchea
(path + método) -- si `maestros` fuera primero, una request a
`/maestros/salud` sería interceptada como `entidad="salud"` (404 "maestro
desconocido") en vez de llegar al tablero de salud real. `carga` no tiene
este problema (sus rutas tienen un segmento extra, `/maestros/{entidad}/
carga[...]`), así que su posición relativa a `maestros` no importa.
"""
from fastapi import APIRouter

from app.motored.api import (
    auth,
    bot,
    bot_demanda_perdida,
    cargas,
    carga,
    demanda_perdida,
    maestros,
    parametros,
    salud,
    usuarios,
)

router = APIRouter()

router.include_router(auth.router)
router.include_router(salud.router)  # antes de maestros -- ver nota arriba
router.include_router(maestros.router)
router.include_router(carga.router)
router.include_router(usuarios.router)
router.include_router(parametros.router)
# Fase 2 "Ingesta" (sdd/motored-pedidos-ingesta, task 9.4): `/cargas` es un
# prefijo propio (`/api/motored/cargas`), sin superposición de path con
# ninguno de los routers de arriba -- el orden relativo no importa acá,
# a diferencia del caso `salud`/`maestros` documentado más arriba.
router.include_router(cargas.router)
# sdd/motored-ventas-perdidas-bot, Phase 5: `/bot` es también un prefijo
# propio (`/api/motored/bot`), sin superposición con ninguno de los de
# arriba -- el orden relativo tampoco importa acá.
router.include_router(bot.router)
# sdd/motored-ventas-perdidas-bot, Phase 6 fix-up (finding #6): superficie
# de demanda perdida del bot, extraída de `bot.py` a su propio archivo --
# MISMO prefijo `/bot` que el router de arriba (FastAPI permite 2 routers
# con el mismo prefix montados por separado mientras sus paths no se
# superpongan; no lo hacen -- ver el docstring de `bot_demanda_perdida.py`).
router.include_router(bot_demanda_perdida.router)
# sdd/motored-ventas-perdidas-bot, Phase 6: `/demanda-perdida` es otro
# prefijo propio (`/api/motored/demanda-perdida`), sin superposición.
router.include_router(demanda_perdida.router)
