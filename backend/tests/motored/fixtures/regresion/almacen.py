"""
Motored Pedidos F3 "Motor" (S8b) — una corrida "persistida" en memoria para
probar los adaptadores de base de datos de los informes sin Postgres.

El motor puro corre y se persiste con las MISMAS funciones de escritura que
usa `guardar_sucursal` (`persistencia.armar_filas`); una sesión de juguete
sirve las tablas por nombre. Sólo datos inventados.
"""
import dataclasses
import datetime
import uuid

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_resumen import CorridaResumen
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.services import parametros
from app.motored.services.corridas import parametros_corrida as pcorr
from app.motored.services.corridas import persistencia as pe
from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.sustitucion import resolver_cadenas
from tests.motored.conftest import _ExecuteResult

CORTE = datetime.date(2026, 9, 21)
SELECCION = {
    "antiguedad": {
        "inventario": {
            "carga_id": "c1", "fecha_usada": "2026-09-19",
            "antiguedad_dias": 2, "limite_dias": 7, "fuente_limite": "DEFAULT",
        },
    },
    "mes_en_curso": {"modo_efectivo": "EXCLUIDO", "d": None, "D": None},
    "advertencias": [
        {"codigo": "A-CORRIDA-101", "mensaje": "Sin demanda perdida"},
    ],
}


class Almacen:
    """Lo que el motor dejó persistido, servido por una sesión de juguete."""

    def __init__(self, corrida, sucursales, lineas, resumen):
        self.corrida = corrida
        self.sucursales = sucursales
        self.lineas = lineas
        self.resumen = resumen

    async def execute(self, sentencia):
        tabla = sentencia.get_final_froms()[0].name
        return _ExecuteResult({
            "corrida": [self.corrida],
            "corrida_sucursal": self.sucursales,
            "corrida_linea": self.lineas,
            "corrida_resumen": self.resumen,
        }[tabla])


def almacenar(sucursales, *, overrides=None, nodos=(), seleccion=None):
    """Corre el motor por sucursal y lo persiste en memoria."""
    ids = [a.sucursal_id for a, _ in sucursales]
    vigentes = parametros.VigentesMotor.desde_filas(
        [], CORTE, overrides=overrides)
    params = pcorr.construir_parametros_corrida(vigentes, ids)
    resoluciones = resolver_cadenas({n.referencia_id: n for n in nodos})
    consolidar = params.motor.consolidar_sustituidas
    corrida = Corrida(
        id=uuid.uuid4(), codigo="PED-2026-S39-001", estado="BORRADOR",
        fecha_corte=CORTE, parametros_snapshot=params.snapshot,
        seleccion_datos=seleccion or SELECCION,
        maestro_sustitucion=[
            {"referencia_id": str(n.referencia_id), "activa": n.activa,
             "sustituida_por": None if n.sustituida_por is None
             else str(n.sustituida_por)} for n in nodos])
    filas_sucursal, lineas, resumen = [], [], []
    for orden, (sucursal, entradas) in enumerate(sucursales, 1):
        resultado = calcular_sucursal(
            entradas, sucursal, params.motor, resoluciones)
        filas = pe.armar_filas(
            corrida.id, sucursal, entradas, resultado, consolidar=consolidar)
        filas_sucursal.append(CorridaSucursal(
            corrida_id=corrida.id, sucursal_id=sucursal.sucursal_id,
            orden=orden, **filas.sucursal))
        lineas += [CorridaLinea(**f) for f in filas.lineas]
        resumen += [CorridaResumen(**f) for f in filas.resumen]
    return Almacen(corrida, filas_sucursal, lineas, resumen)


def con_sucursal_id(atributos, sucursal_id):
    """Las mismas atribuciones con un id conocido por el test."""
    return dataclasses.replace(atributos, sucursal_id=sucursal_id)
