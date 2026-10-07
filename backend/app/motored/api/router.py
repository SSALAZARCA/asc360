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
from fastapi import APIRouter, Depends, HTTPException, status

from app.motored.services.kpi_resumen import ResumenOcupadoError
from app.motored.api import (
    auth,
    avisos_antiguedad,
    bot,
    bot_demanda_perdida,
    cargas,
    carga,
    clientes_tecnired,
    corridas,
    corridas_pedido,
    corridas_vistas,
    demanda_perdida,
    detractores,
    encuesta_cargas,
    encuesta_publica,
    inicio,
    maestros,
    parametros,
    presupuestos,
    publico_informe,
    referencias_busqueda,
    reporte_asesor,
    salud,
    tablero_asesores,
    tablero_kpis,
    usuarios,
    vendedores,
)

MENSAJE_RESUMEN_OCUPADO = "Los indicadores se están recalculando; intente de nuevo en unos minutos."


async def _traducir_resumen_ocupado():
    """A write that needs the KPI summaries' advisory lock (carga apply/annul, Configuracion,
    referencias, Tecnired, recalcular) gives up after `MOTORED_KPI_RESUMEN_LOCK_TIMEOUT_SEGUNDOS`
    while a full rebuild runs. That is a retryable conflict, never a 500. FastAPI has no
    per-router exception handlers, so this router-level dependency (it sees the endpoint's
    exceptions) maps it to one 409 for EVERY Motored endpoint."""
    try:
        yield
    except ResumenOcupadoError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=MENSAJE_RESUMEN_OCUPADO)


router = APIRouter(dependencies=[Depends(_traducir_resumen_ocupado)])

router.include_router(auth.router)
router.include_router(salud.router)  # antes de maestros -- ver nota arriba
# Tambien antes de maestros: `/maestros/referencias/buscar` chocaria con el
# generico `/maestros/{entidad}/{entity_id}` (ver `referencias_busqueda.py`).
router.include_router(referencias_busqueda.router)
router.include_router(maestros.router)
router.include_router(carga.router)
# T2 tablero-asesores: `/clientes-tecnired` es un prefijo propio, sin superposicion.
router.include_router(clientes_tecnired.router)
# T3 tablero-asesores: `/vendedores` es un prefijo propio, sin superposicion.
router.include_router(vendedores.router)
# T4 tablero-asesores: `/tablero-asesores` es un prefijo propio, solo ADMIN|COMPRAS.
router.include_router(tablero_asesores.router)
# KPI's (motored-kpis, B6): cuelga de `/tablero-asesores/kpis`, dentro del prefijo de GERENCIA.
router.include_router(tablero_kpis.router)
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
# Satisfaction survey (T3): `/encuesta/cargas` is its own prefix, no path
# overlap with any router above -- registration order does not matter.
router.include_router(encuesta_cargas.router)
# Satisfaction survey (T4): PUBLIC `/encuesta/publico` (no auth, rate-limited).
router.include_router(encuesta_publica.router)
router.include_router(publico_informe.router)
# Satisfaction survey (T5): `/detractores` is its own prefix, no path overlap.
router.include_router(detractores.router)
# Fase 3 "Motor" (sdd/motored-pedidos-motor, S7): `/corridas` es su propio
# prefijo (`/api/motored/corridas`), sin superposición de path con ninguno de
# los routers de arriba -- el orden relativo no importa acá.
router.include_router(corridas.router)
# Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B2): las acciones por
# tienda de `/corridas` viven en su propio router, mismo prefijo, rutas
# distintas (`/{id}/lineas/{linea_id}...`): el orden relativo no importa.
router.include_router(corridas_pedido.router)
# Fase 4 (B6): las vistas de la red (consolidado y comparación de un
# escenario) tienen su propio router, mismo prefijo, rutas distintas
# (`/{id}/consolidado`, `/{id}/comparar`): el orden relativo no importa.
router.include_router(corridas_vistas.router)
# Aviso anticipado de antigüedad de datos: `/avisos-antiguedad` es su propio
# prefijo (`/api/motored/avisos-antiguedad`), sin superposición de path.
router.include_router(avisos_antiguedad.router)
# Sales budgets per asesor (ADMIN|GERENCIA): `/presupuestos` is its own prefix,
# no path overlap with any router above.
router.include_router(presupuestos.router)
# Welcome page ("Inicio"): `/inicio` is its own prefix, no path overlap.
router.include_router(inicio.router)
# Daily asesor report (ADMIN): `/reporte-asesor` is its own prefix.
router.include_router(reporte_asesor.router)
