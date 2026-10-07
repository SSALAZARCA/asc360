"""
Motored Pedidos — paquete de modelos (sdd/motored-pedidos-cimientos, Fase 3,
task 3.1; sdd/motored-pedidos-ingesta, Fase 2 Phase 1 task 1.1, Phase 3 task
3.1; sdd/motored-ventas-perdidas-bot, Phase 1 "Schema";
sdd/motored-pedidos-motor, S4a, tablas `corrida*`; sdd/motored-pedidos-ui,
Fase 4, B1, historial de edicion, eventos y envios). Importar este
paquete registra todos los modelos en `MotoredBase.metadata` -- requerido por
`alembic_motored/env.py` para el autogenerate y por cualquier `create_all()`
de test.
"""
from app.motored.models.auditoria_maestro import AuditoriaMaestro
from app.motored.models.backorder_linea import BackorderLinea
from app.motored.models.bodega import Bodega
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_error import CargaError
from app.motored.models.caso_detractor import CasoDetractor
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.models.caso_detractor_accion import CasoDetractorAccion
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.corrida import Corrida
from app.motored.models.corrida_carga import CorridaCarga
from app.motored.models.corrida_envio import CorridaEnvio
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_linea_historial import CorridaLineaHistorial
from app.motored.models.corrida_resumen import CorridaResumen
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.demanda_perdida import DemandaPerdida
from app.motored.models.demanda_perdida_bot_linea import DemandaPerdidaBotLinea
from app.motored.models.encuesta_carga import EncuestaCarga
from app.motored.models.encuesta_registro import EncuestaRegistro
from app.motored.models.encuesta_respuesta import EncuestaRespuesta
from app.motored.models.factura_proveedor_linea import FacturaProveedorLinea
from app.motored.models.ingreso_factura import IngresoFactura
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.inventario_snapshot import InventarioSnapshot
from app.motored.models.kpi_resumen import (
    KpiClienteMes, KpiCostoReferencia, KpiFacturaFirma, KpiInventarioCorte, KpiResumenEstado, KpiVentaMes,
)
from app.motored.models.login_evento import LoginEvento
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.models.pedido_evento import PedidoEvento
from app.motored.models.presupuesto import PresupuestoLinea, PresupuestoVersion
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.reporte_asesor_envio import ReporteAsesorEnvio
from app.motored.models.reporte_asesor_link import ReporteAsesorLink
from app.motored.models.retencion_ejecucion import RetencionEjecucion
from app.motored.models.sucursal import Sucursal
from app.motored.models.sucursal_alias import SucursalAlias
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.usuario_sucursal import UsuarioSucursal
from app.motored.models.vendedor import Vendedor
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.models.venta_mensual import VentaMensual

__all__ = [
    "AuditoriaMaestro",
    "BackorderLinea",
    "Bodega",
    "CargaArchivo",
    "CargaError",
    "CasoDetractor",
    "ClienteTecnired",
    "CasoDetractorAccion",
    "CargaFilaStaging",
    "Corrida",
    "CorridaCarga",
    "CorridaEnvio",
    "CorridaLinea",
    "CorridaLineaHistorial",
    "CorridaResumen",
    "CorridaSucursal",
    "DemandaPerdida",
    "DemandaPerdidaBotLinea",
    "EncuestaCarga",
    "EncuestaRegistro",
    "EncuestaRespuesta",
    "FacturaProveedorLinea",
    "IngresoFactura",
    "InventarioDetalle",
    "InventarioSnapshot",
    "KpiClienteMes",
    "KpiCostoReferencia",
    "KpiFacturaFirma",
    "KpiInventarioCorte",
    "KpiResumenEstado",
    "KpiVentaMes",
    "LoginEvento",
    "ParametroMetodologia",
    "PedidoEvento",
    "PresupuestoLinea",
    "PresupuestoVersion",
    "Proveedor",
    "Referencia",
    "ReporteAsesorEnvio",
    "ReporteAsesorLink",
    "RetencionEjecucion",
    "Sucursal",
    "SucursalAlias",
    "MotoredRole",
    "Usuario",
    "UsuarioSucursal",
    "Vendedor",
    "VentaDetalle",
    "VentaMensual",
]
