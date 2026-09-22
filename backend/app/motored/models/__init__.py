"""
Motored Pedidos — paquete de modelos (sdd/motored-pedidos-cimientos, Fase 3,
task 3.1; sdd/motored-pedidos-ingesta, Fase 2 Phase 1, task 1.1). Importar
este paquete registra los 13 modelos en `MotoredBase.metadata` -- requerido
por `alembic_motored/env.py` para el autogenerate y por cualquier
`create_all()` de test.
"""
from app.motored.models.auditoria_maestro import AuditoriaMaestro
from app.motored.models.bodega import Bodega
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.retencion_ejecucion import RetencionEjecucion
from app.motored.models.sucursal import Sucursal
from app.motored.models.sucursal_alias import SucursalAlias
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.usuario_sucursal import UsuarioSucursal

__all__ = [
    "AuditoriaMaestro",
    "Bodega",
    "CargaArchivo",
    "CargaError",
    "CargaFilaStaging",
    "ParametroMetodologia",
    "Proveedor",
    "Referencia",
    "RetencionEjecucion",
    "Sucursal",
    "SucursalAlias",
    "MotoredRole",
    "Usuario",
    "UsuarioSucursal",
]
