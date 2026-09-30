"""
Motored Pedidos F3 "Motor" (S8b, ADR-10, spec Domain 4 nivel C) — medición
del efecto de cada switch de desviación.

Desde la línea base (todos los switches apagados, el preset legacy) se corre un
escenario por switch encendido SOLO, y uno con todos juntos. Cada escenario
produce un delta frente a la base: líneas cambiadas, unidades, valor,
movimientos de clase y líneas transferidas. No hay pasa/falla: es medición
para que el dueño decida qué switch activar.

Los escenarios son diccionarios de overrides con las mismas claves del
registro de parámetros (`POST /corridas` los acepta tal cual), de modo que el
mismo escenario corre de dos maneras:

- **en memoria** (`medir_en_memoria`): el motor puro sobre los insumos que se
  tengan (por ejemplo los del libro de Excel). Un switch cuyos insumos no
  están (demanda perdida por mes, maestro de sustitución, mes en curso) o que
  actúa en el cargador (tránsito vencido) queda "no medido" con el motivo;
- **con base de datos** (`delta_db`): una corrida escenario real por switch.

El preset de producción nunca se toca: los overrides viven sólo en el
escenario y la base de parámetros es inmutable.
"""
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence
from uuid import UUID

from app.motored.services.motor.aritmetica import a_fraccion, cuantizar
from app.motored.services.motor.motor import (
    ResultadoSucursal,
    calcular_sucursal,
)
from app.motored.services.motor.tipos import (
    AtributosSucursal,
    EntradaReferencia,
    MesEnCurso,
    ParametrosMotor,
    Resolucion,
)

NOMBRE_BASE = "Línea base (todo apagado)"
NOMBRE_COMBINADO = "combinado"
TIPO_CAMBIO = "CAMBIO"
TIPO_NUEVA = "NUEVA"
TIPO_QUITADA = "QUITADA"
ESCALA_N = 6
ESCALA_DINERO = 2
MINIMO_SWITCHES_COMBINADO = 2

CLAVE_PERDIDA = "incluir_demanda_perdida_en_ponderada"
CLAVE_FACTOR = "factor_demanda_perdida"
CLAVE_CONSOLIDAR = "consolidar_sustituidas"
CLAVE_DIAS = "dias_entre_pedidos"
CLAVE_MES = "modo_mes_en_curso"
CLAVE_TRANSITO = "excluir_transito_vencido"

MOTIVO_SIN_PERDIDA = "los insumos no traen demanda perdida por mes"
MOTIVO_SIN_MAESTRO = "los insumos no traen maestro de sustitución"
MOTIVO_SIN_MES = (
    "los insumos no traen el mes en curso (ventas de M0 y días transcurridos)"
)
MOTIVO_TRANSITO = (
    "recalcula el tránsito al corte en el cargador: sólo se mide con base "
    "de datos"
)


@dataclass(frozen=True)
class Escenario:
    """Un switch (o varios) encendidos, como overrides del registro."""

    nombre: str
    descripcion: str
    overrides: Mapping[str, Any]


@dataclass(frozen=True)
class LineaComparable:
    """Lo que se compara de una línea, cuantizado como al persistir."""

    codigo: str
    clase: str
    n: Decimal
    pedido: Decimal
    valor: Decimal


@dataclass(frozen=True)
class Excluida:
    """Referencia que salió del pedido por la consolidación."""

    codigo: str
    motivo: str
    sustituta: Optional[str]


@dataclass(frozen=True)
class ConjuntoLineas:
    """Líneas del pedido de una sucursal (por código) y sus excluidas."""

    lineas: Mapping[str, LineaComparable]
    excluidas: tuple[Excluida, ...]


@dataclass(frozen=True)
class CambioLinea:
    """Una línea que difiere entre la base y el escenario."""

    codigo: str
    tipo: str
    clase_base: Optional[str]
    n_base: Optional[Decimal]
    pedido_base: Optional[Decimal]
    valor_base: Optional[Decimal]
    clase_escenario: Optional[str]
    n_escenario: Optional[Decimal]
    pedido_escenario: Optional[Decimal]
    valor_escenario: Optional[Decimal]


@dataclass(frozen=True)
class DeltaEscenario:
    """Efecto de un escenario frente a la base.

    `lineas_cambiadas` cuenta las líneas con pedido distinto (incluidas las
    nuevas o quitadas con pedido); `cambios` trae además las que sólo
    cambian de N, de clase o de valor.
    """

    lineas_base: int
    lineas_escenario: int
    lineas_cambiadas: int
    movimientos_clase: int
    unidades_base: Decimal
    unidades_escenario: Decimal
    valor_base: Decimal
    valor_escenario: Decimal
    cambios: tuple[CambioLinea, ...]
    transferidas: tuple[Excluida, ...]


@dataclass(frozen=True)
class ResultadoEscenario:
    """Un escenario medido (`delta`) o no medido (`motivo_no_medido`)."""

    escenario: Escenario
    conjunto: Optional[ConjuntoLineas]
    delta: Optional[DeltaEscenario]
    motivo_no_medido: Optional[str] = None
    nota: Optional[str] = None


@dataclass(frozen=True)
class InsumosMemoria:
    """Insumos de una sucursal para medir con el motor puro.

    `mes_en_curso` es la configuración efectiva de M0 (PONDERADO con sus
    `d`, `D` y tope) y sólo se usa si las entradas traen `venta_m0`.
    """

    entradas: tuple[EntradaReferencia, ...]
    atributos: AtributosSucursal
    params: ParametrosMotor
    resoluciones: Mapping[UUID, Resolucion] = field(default_factory=dict)
    mes_en_curso: Optional[MesEnCurso] = None


# --- Escenarios -------------------------------------------------------------


def _texto_numero(valor) -> str:
    return format(Decimal(str(valor)).normalize(), "f")


def escenarios_estandar(factores: Sequence = (1,),
                        dias: Sequence[int] = (7, 15)
                        ) -> tuple[Escenario, ...]:
    """Un escenario por switch encendido solo, y el combinado al final."""
    factores = tuple(_texto_numero(f) for f in factores)
    perdida = [
        Escenario(
            f"perdida x{f}", f"Demanda perdida ON, factor {f}",
            {CLAVE_PERDIDA: True, CLAVE_FACTOR: f},
        )
        for f in factores
    ]
    por_dias = [
        Escenario(
            f"{CLAVE_DIAS}={d}", f"Período de revisión de {d} días",
            {CLAVE_DIAS: d},
        )
        for d in dias
    ]
    solos = [
        *perdida,
        Escenario(
            CLAVE_CONSOLIDAR, "Consolidación de sustituidas ON",
            {CLAVE_CONSOLIDAR: True},
        ),
        *por_dias,
        Escenario(
            "mes_en_curso=PONDERADO", "Mes en curso PONDERADO",
            {CLAVE_MES: "PONDERADO"},
        ),
        Escenario(
            CLAVE_TRANSITO, "Excluir tránsito vencido ON",
            {CLAVE_TRANSITO: True},
        ),
    ]
    return (*solos, _combinado(factores, dias))


def _combinado(factores: Sequence[str], dias: Sequence[int]) -> Escenario:
    overrides: dict[str, Any] = {
        CLAVE_PERDIDA: True, CLAVE_FACTOR: factores[0],
        CLAVE_CONSOLIDAR: True, CLAVE_DIAS: dias[0],
        CLAVE_MES: "PONDERADO", CLAVE_TRANSITO: True,
    }
    return Escenario(
        NOMBRE_COMBINADO,
        "Todos los switches encendidos a la vez (primer factor y primer "
        "período de revisión)",
        overrides,
    )


# --- Conjuntos comparables --------------------------------------------------


def conjunto_desde_resultado(resultado: ResultadoSucursal) -> ConjuntoLineas:
    """Líneas y excluidas del motor, cuantizadas como al persistir."""
    lineas = {
        linea.entrada.codigo: LineaComparable(
            linea.entrada.codigo, linea.clase,
            cuantizar(linea.n, ESCALA_N),
            cuantizar(linea.pedido, ESCALA_DINERO),
            cuantizar(linea.valor_pedido, ESCALA_DINERO),
        )
        for linea in resultado.lineas
    }
    excluidas = tuple(
        Excluida(e.entrada.codigo, e.motivo, e.sustituta_final_codigo)
        for e in resultado.excluidas
    )
    return ConjuntoLineas(lineas, excluidas)


# --- Delta ------------------------------------------------------------------


def _cambio(codigo: str, base: Optional[LineaComparable],
            escenario: Optional[LineaComparable]) -> Optional[CambioLinea]:
    if base is not None and escenario is not None and base == escenario:
        return None
    tipo = (
        TIPO_NUEVA if base is None
        else TIPO_QUITADA if escenario is None else TIPO_CAMBIO
    )
    return CambioLinea(codigo, tipo, *_campos(base), *_campos(escenario))


def _campos(linea: Optional[LineaComparable]) -> tuple:
    if linea is None:
        return (None, None, None, None)
    return (linea.clase, linea.n, linea.pedido, linea.valor)


def _suma(conjunto: ConjuntoLineas, campo: str) -> Decimal:
    return sum(
        (getattr(linea, campo) for linea in conjunto.lineas.values()),
        Decimal(0),
    )


def _codigos(base: ConjuntoLineas, escenario: ConjuntoLineas) -> list[str]:
    nuevos = [c for c in escenario.lineas if c not in base.lineas]
    return [*base.lineas, *nuevos]


def calcular_delta(base: ConjuntoLineas, escenario: ConjuntoLineas
                   ) -> DeltaEscenario:
    """Delta del escenario frente a la base (ver `DeltaEscenario`)."""
    cambios = tuple(
        cambio for cambio in (
            _cambio(c, base.lineas.get(c), escenario.lineas.get(c))
            for c in _codigos(base, escenario)
        ) if cambio is not None
    )
    return DeltaEscenario(
        lineas_base=len(base.lineas),
        lineas_escenario=len(escenario.lineas),
        lineas_cambiadas=sum(
            1 for c in cambios
            if (c.pedido_base or 0) != (c.pedido_escenario or 0)
        ),
        movimientos_clase=sum(
            1 for c in cambios
            if c.tipo == TIPO_CAMBIO and c.clase_base != c.clase_escenario
        ),
        unidades_base=_suma(base, "pedido"),
        unidades_escenario=_suma(escenario, "pedido"),
        valor_base=_suma(base, "valor"),
        valor_escenario=_suma(escenario, "valor"),
        cambios=cambios,
        transferidas=tuple(
            e for e in escenario.excluidas if e.sustituta is not None
        ),
    )


# --- Medición en memoria ----------------------------------------------------


def _motivo_perdida(insumos: InsumosMemoria) -> Optional[str]:
    hay = any(any(e.perdidas) for e in insumos.entradas)
    return None if hay else MOTIVO_SIN_PERDIDA


def _motivo_consolidar(insumos: InsumosMemoria) -> Optional[str]:
    hay = any(r.motivo is not None for r in insumos.resoluciones.values())
    return None if hay else MOTIVO_SIN_MAESTRO


def _motivo_mes(insumos: InsumosMemoria) -> Optional[str]:
    hay = insumos.mes_en_curso is not None and any(
        e.venta_m0 is not None for e in insumos.entradas
    )
    return None if hay else MOTIVO_SIN_MES


def _sin_motivo(insumos: InsumosMemoria) -> Optional[str]:
    return None


def _motivo_transito(insumos: InsumosMemoria) -> Optional[str]:
    return MOTIVO_TRANSITO


# switch -> (claves que lo forman, verificación de insumos)
GRUPOS: Mapping[str, tuple[tuple[str, ...], Callable]] = {
    "perdida": ((CLAVE_PERDIDA, CLAVE_FACTOR), _motivo_perdida),
    "consolidar": ((CLAVE_CONSOLIDAR,), _motivo_consolidar),
    "dias": ((CLAVE_DIAS,), _sin_motivo),
    "mes": ((CLAVE_MES,), _motivo_mes),
    "transito": ((CLAVE_TRANSITO,), _motivo_transito),
}


def _grupo_de(clave: str) -> Optional[str]:
    for nombre, (claves, _) in GRUPOS.items():
        if clave in claves:
            return nombre
    return None


def _aplicar_perdida(estado: list, valor) -> None:
    estado[0] = replace(estado[0], incluir_demanda_perdida=bool(valor))


def _aplicar_factor(estado: list, valor) -> None:
    factor = a_fraccion(Decimal(str(valor)))
    estado[0] = replace(estado[0], factor_demanda_perdida=factor)


def _aplicar_consolidar(estado: list, valor) -> None:
    estado[0] = replace(estado[0], consolidar_sustituidas=bool(valor))


def _aplicar_dias(estado: list, valor) -> None:
    estado[1] = replace(estado[1], dias_entre_pedidos=Decimal(str(valor)))


_APLICACIONES: Mapping[str, Callable[[list, Any], None]] = {
    CLAVE_PERDIDA: _aplicar_perdida,
    CLAVE_FACTOR: _aplicar_factor,
    CLAVE_CONSOLIDAR: _aplicar_consolidar,
    CLAVE_DIAS: _aplicar_dias,
}


def _configurar(insumos: InsumosMemoria, overrides: Mapping[str, Any]
                ) -> tuple[ParametrosMotor, AtributosSucursal]:
    estado = [insumos.params, insumos.atributos]
    for clave, valor in overrides.items():
        if clave == CLAVE_MES and valor == "PONDERADO":
            estado[0] = replace(estado[0], mes_en_curso=insumos.mes_en_curso)
        elif clave in _APLICACIONES:
            _APLICACIONES[clave](estado, valor)
    return estado[0], estado[1]


def _correr(insumos: InsumosMemoria, overrides: Mapping[str, Any]
            ) -> ConjuntoLineas:
    params, atributos = _configurar(insumos, overrides)
    resultado = calcular_sucursal(
        insumos.entradas, atributos, params, insumos.resoluciones
    )
    return conjunto_desde_resultado(resultado)


def _evaluar_grupos(insumos: InsumosMemoria, overrides: Mapping[str, Any]
                    ) -> tuple[dict[str, Any], dict[str, str]]:
    """`(overrides aplicables, {clave: motivo de no poder medirla})`.

    De un switch con varias claves sólo se informa la primera omitida.
    """
    aplicables: dict[str, Any] = {}
    omitidos: dict[str, str] = {}
    vistos: set[str] = set()
    for clave, valor in overrides.items():
        grupo = _grupo_de(clave)
        motivo = (
            f"la clave {clave} no se aplica en memoria" if grupo is None
            else GRUPOS[grupo][1](insumos)
        )
        if motivo is None:
            aplicables[clave] = valor
        elif grupo not in vistos:
            omitidos[clave] = motivo
            vistos.add(grupo)
    return aplicables, omitidos


def _nota(aplicables: Mapping[str, Any], omitidos: Mapping[str, str]) -> str:
    incluye = ", ".join(aplicables)
    if not omitidos:
        return f"Incluye: {incluye}."
    sin = "; ".join(f"{k} ({m})" for k, m in omitidos.items())
    return f"Incluye: {incluye}. Omitidos: {sin}."


def _cuantos_switches(aplicables: Mapping[str, Any]) -> int:
    return len({_grupo_de(clave) for clave in aplicables})


def _medir(insumos: InsumosMemoria, base: ConjuntoLineas,
           escenario: Escenario) -> ResultadoEscenario:
    aplicables, omitidos = _evaluar_grupos(insumos, escenario.overrides)
    compuesto = _cuantos_switches(escenario.overrides) > 1
    minimo = MINIMO_SWITCHES_COMBINADO if compuesto else 1
    if _cuantos_switches(aplicables) < minimo:
        motivo = (
            "el combinado necesita al menos dos switches medibles con "
            "estos insumos" if compuesto else next(iter(omitidos.values()))
        )
        return ResultadoEscenario(escenario, None, None, motivo)
    conjunto = _correr(insumos, aplicables)
    nota = _nota(aplicables, omitidos) if compuesto else None
    return ResultadoEscenario(
        escenario, conjunto, calcular_delta(base, conjunto), None, nota
    )


def medir_en_memoria(insumos: InsumosMemoria,
                     escenarios: Iterable[Escenario]
                     ) -> tuple[ResultadoEscenario, ...]:
    """Base y escenarios con el motor puro; la base va siempre primero."""
    base = _correr(insumos, {})
    linea_base = Escenario(
        NOMBRE_BASE, "Todos los switches en su valor legacy", {}
    )
    resultados = [ResultadoEscenario(linea_base, base, None)]
    resultados += [_medir(insumos, base, e) for e in escenarios]
    return tuple(resultados)
