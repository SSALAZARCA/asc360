"""
Motored Pedidos — paquete de modelos (sdd/motored-pedidos-cimientos, Fase 3,
task 3.1; sdd/motored-pedidos-ingesta, Fase 2 Phase 1 task 1.1, Phase 3 task
3.1; sdd/motored-ventas-perdidas-bot, Phase 1 "Schema"). Importar este
paquete registra los 20 modelos en `MotoredBase.metadata` -- requerido por
`alembic_motored/env.py` para el autogenerate y por cualquier `create_all()`
de test.
"""
from app.motored.models.auditoria_maestro import AuditoriaMaestro
from app.motored.models.backorder_linea import BackorderLinea
from app.motored.models.bodega import Bodega
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.demanda_perdida import DemandaPerdida
from app.motored.models.demanda_perdida_bot_linea import DemandaPerdidaBotLinea
from app.motored.models.factura_proveedor_linea import FacturaProveedorLinea
from app.motored.models.ingreso_factura import IngresoFactura
from app.motored.models.inventario_snapshot import InventarioSnapshot
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.retencion_ejecucion import RetencionEjecucion
from app.motored.models.sucursal import Sucursal
from app.motored.models.sucursal_alias import SucursalAlias
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.usuario_sucursal import UsuarioSucursal
from app.motored.models.venta_mensual import VentaMensual

__all__ = [
    "AuditoriaMaestro",
    "BackorderLinea",
    "Bodega",
    "CargaArchivo",
    "CargaError",
    "CargaFilaStaging",
    "DemandaPerdida",
    "DemandaPerdidaBotLinea",
    "FacturaProveedorLinea",
    "IngresoFactura",
    "InventarioSnapshot",
    "ParametroMetodologia",
    "Proveedor",
    "Referencia",
    "RetencionEjecucion",
    "Sucursal",
    "SucursalAlias",
    "MotoredRole",
    "Usuario",
    "UsuarioSucursal",
    "VentaMensual",
]
