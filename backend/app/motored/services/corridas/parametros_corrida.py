"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S4b, ADR-7, decisión
#16): parámetros congelados de UNA corrida y su snapshot.

Toma las versiones vigentes al corte (`VigentesMotor`), aplica la precedencia
override > sucursal > global > default y entrega:

- `motor`: los `ParametrosMotor` del motor puro;
- `dias_entre_pedidos` por sucursal y los cuatro límites de antigüedad de
  datos (un límite por tipo: afectan SÓLO la compuerta de vigencia);
- los valores que el preflight (S5a) necesita para el mes en curso;
- `snapshot`: JSON puro con el valor y la FUENTE de cada parámetro.

Todo es puro salvo `cargar_parametros_corrida`, que hace una sola lectura.
"""
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Any, Mapping, Optional, Sequence
from uuid import UUID

from app.motored.services import parametros, parametros_claves as pc
from app.motored.services.corridas import codigos
from app.motored.services.motor.tipos import ParametrosMotor
from app.motored.services.parametros import ResolucionParametro

CLAVE_DIAS_ENTRE_PEDIDOS = "dias_entre_pedidos"


@dataclass(frozen=True)
class ParametrosCorrida:
    motor: ParametrosMotor
    dias_entre_pedidos: Mapping[UUID, int]
    limites_antiguedad: Mapping[str, int]
    modo_mes_en_curso: str
    tope_mes_en_curso: Fraction
    min_dias_mes_en_curso: int
    excluir_transito_vencido: bool
    snapshot: Mapping[str, Any]


def validar_overrides(overrides: Optional[Mapping[str, Any]]) -> None:
    """Valida los overrides de un escenario; E-CORRIDA-010 si alguno falla.

    Sólo se aceptan claves del motor (no las de la ingesta), con la misma
    regla de valores que `POST /parametros`, y siempre en alcance global.
    """
    for clave, valor in (overrides or {}).items():
        espec = pc.REGISTRO.get(clave)
        if espec is None or espec.grupo != pc.GRUPO_MOTOR:
            raise _override_invalido(clave, "no es un parámetro del motor")
        try:
            pc.validar_escritura(clave, valor)
        except pc.ErrorParametro as error:
            raise _override_invalido(clave, error.mensaje) from error


def _override_invalido(clave: str, detalle: str) -> pc.ErrorParametro:
    codigo = codigos.E_CORRIDA_OVERRIDE_INVALIDO
    return pc.ErrorParametro(
        codigo, codigos.mensaje(codigo, clave=clave, detalle=detalle))


def _entrada(res: ResolucionParametro) -> dict:
    """Entrada de snapshot: valor, fuente y versión de la fila usada."""
    return {
        "valor": res.valor,
        "fuente": res.fuente,
        "parametro_id": None if res.parametro_id is None
        else str(res.parametro_id),
        "vigente_desde": None if res.vigente_desde is None
        else res.vigente_desde.isoformat(),
    }


def _armar_motor(valor) -> ParametrosMotor:
    """`ParametrosMotor` desde una función clave -> valor tipado."""
    return ParametrosMotor(
        incluir_demanda_perdida=valor("incluir_demanda_perdida_en_ponderada"),
        factor_demanda_perdida=valor("factor_demanda_perdida"),
        consolidar_sustituidas=valor("consolidar_sustituidas"),
        modo_redondeo=valor("modo_redondeo_empaque"),
        corte_abc_a=valor("corte_abc_a"),
        corte_abc_b=valor("corte_abc_b"),
        umbral_f=valor("umbral_f"),
        umbral_m=valor("umbral_m"),
        k_fms=valor("k_fms"),
        tolerancia_sobrestock=valor("tolerancia_sobrestock"),
        meses_inventario_muerto=valor("meses_inventario_muerto"),
    )


def _dias_por_sucursal(vigentes, sucursal_ids) -> tuple:
    """`(dias por sucursal, entradas de snapshot por sucursal)`."""
    dias, entradas = {}, {}
    for sucursal_id in sucursal_ids:
        res = vigentes.resolver(CLAVE_DIAS_ENTRE_PEDIDOS, sucursal_id)
        dias[sucursal_id] = pc.parsear(CLAVE_DIAS_ENTRE_PEDIDOS, res.valor)
        entradas[str(sucursal_id)] = _entrada(res)
    return dias, entradas


def _limites(vigentes) -> tuple:
    """`(días por tipo, entradas de snapshot por tipo)` de antigüedad."""
    dias, entradas = {}, {}
    for tipo, clave in pc.CLAVES_ANTIGUEDAD.items():
        res = vigentes.resolver(clave)
        dias[tipo] = pc.parsear(clave, res.valor)
        entradas[tipo] = {
            "clave": clave, "dias": res.valor, "fuente": res.fuente}
    return dias, entradas


def construir_parametros_corrida(
    vigentes: "parametros.VigentesMotor", sucursal_ids: Sequence[UUID],
) -> ParametrosCorrida:
    """Congela los parámetros de la corrida y arma su snapshot."""
    resoluciones = {c: vigentes.resolver(c) for c in pc.claves_motor()}

    def valor(clave: str) -> Any:
        return pc.parsear(clave, resoluciones[clave].valor)

    dias, dias_snapshot = _dias_por_sucursal(vigentes, sucursal_ids)
    limites, limites_snapshot = _limites(vigentes)
    snapshot = {
        "parametros_en_fecha": vigentes.en_fecha.isoformat(),
        "parametros": {c: _entrada(r) for c, r in resoluciones.items()},
        "dias_entre_pedidos_por_sucursal": dias_snapshot,
        "limites_antiguedad": limites_snapshot,
    }
    return ParametrosCorrida(
        motor=_armar_motor(valor),
        dias_entre_pedidos=dias,
        limites_antiguedad=limites,
        modo_mes_en_curso=valor("modo_mes_en_curso"),
        tope_mes_en_curso=valor("tope_proyeccion_mes_actual"),
        min_dias_mes_en_curso=valor("min_dias_mes_actual"),
        excluir_transito_vencido=valor("excluir_transito_vencido"),
        snapshot=snapshot,
    )


async def cargar_parametros_corrida(
    db,
    en_fecha: date,
    sucursal_ids: Sequence[UUID],
    overrides: Optional[Mapping[str, Any]] = None,
) -> ParametrosCorrida:
    """Valida los overrides, hace UNA lectura y congela los parámetros."""
    validar_overrides(overrides)
    vigentes = await parametros.obtener_vigentes_motor(
        db, pc.claves_motor(), en_fecha, overrides)
    return construir_parametros_corrida(vigentes, sucursal_ids)
