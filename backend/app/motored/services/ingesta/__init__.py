"""
Motored Pedidos — Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra"
(sdd/motored-pedidos-ingesta). Infra COMPARTIDA por los transforms de
movimiento (`ventas.py`/`inventario.py`/etc., Fase 4+, todavía no
implementados): `lector.py` (streaming), `columnas.py` (mapeo de
encabezados + fechas Excel), `resolucion.py` (ADR-8, cache-first
sucursal/referencia), `errores.py` (`carga_error` + CSV export).
"""
