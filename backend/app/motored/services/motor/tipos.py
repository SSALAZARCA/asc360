"""
Motored Pedidos F3 "Motor" (ADR-2) — tipos inmutables del motor puro.

Las tuplas de meses cerrados van ordenadas M6..M1, que es el orden de las
columnas E..J del Excel y de los pesos 1..6. Los valores de entrada son
`Decimal` (misma escala que las fuentes) y el motor los convierte a `Fraction`
en su frontera. `ParametrosMotor()` sin argumentos ES el preset legacy.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Literal, Mapping, Optional, Sequence
from uuid import UUID

ModoRedondeo = Literal["CERCANO", "ARRIBA"]
ModoMesEnCurso = Literal["EXCLUIDO", "PONDERADO"]

ESTADO_OK = "OK"
ESTADO_OMITIDA = "OMITIDA"

COD_SUCURSAL_OMITIDA = "A-CORRIDA-102"
COD_CADENA_CICLICA = "A-CORRIDA-103"
COD_MES_EN_CURSO_NO_DISPONIBLE = "A-CORRIDA-105"
COD_MES_EN_CURSO_CORTO = "A-CORRIDA-106"
COD_SUMA_NO_POSITIVA = "A-CORRIDA-110"

MOTIVO_SUSTITUIDA = "SUSTITUIDA"
MOTIVO_SIN_REEMPLAZO = "INACTIVA_SIN_REEMPLAZO"

K_FMS_LEGACY: Mapping[str, Fraction] = MappingProxyType(
    {"F": Fraction(3), "M": Fraction(3, 2), "S": Fraction(1)}
)


@dataclass(frozen=True)
class EntradaReferencia:
    """Insumos de UNA referencia en UNA sucursal (columnas E..J, K, T..Z)."""

    referencia_id: UUID
    codigo: str
    nombre: Optional[str]
    linea_comercial: Optional[str]
    precio: Optional[Decimal]
    unidad_empaque: int
    ventas: tuple[Decimal, ...]
    perdidas: tuple[Decimal, ...]
    venta_m0: Optional[Decimal] = None
    perdida_m0: Optional[Decimal] = None
    inventario: Decimal = Decimal(0)
    transito: Decimal = Decimal(0)
    backorder: Decimal = Decimal(0)
    ajuste: Decimal = Decimal(0)
    banderas: frozenset[str] = frozenset()


@dataclass(frozen=True)
class AtributosSucursal:
    """Atributos de la sucursal que gobiernan ventana y cobertura."""

    sucursal_id: UUID
    nombre: str
    fecha_corte: date
    fecha_apertura: Optional[date]
    dias_empaque: Decimal
    dias_transito: Decimal
    dias_seguridad: Decimal
    dias_entre_pedidos: Decimal


@dataclass(frozen=True)
class MesEnCurso:
    """Configuración efectiva del mes en curso (M0), ya resuelta.

    `None` o `modo` EXCLUIDO significa que M0 no influye en nada.

    En la especificación `d` son los días transcurridos (`dias_transcurridos`)
    y `D` los días del mes (`dias_del_mes`); `tope` es
    `tope_proyeccion_mes_actual`.
    """

    modo: ModoMesEnCurso
    dias_transcurridos: int
    dias_del_mes: int
    tope: Fraction


@dataclass(frozen=True)
class ParametrosMotor:
    """Parámetros del motor; los valores por defecto son el preset legacy."""

    incluir_demanda_perdida: bool = False
    factor_demanda_perdida: Fraction = Fraction(1)
    consolidar_sustituidas: bool = False
    modo_redondeo: ModoRedondeo = "CERCANO"
    corte_abc_a: Fraction = Fraction(4, 5)
    corte_abc_b: Fraction = Fraction(19, 20)
    umbral_f: int = 2
    umbral_m: int = 1
    k_fms: Mapping[str, Fraction] = field(default=K_FMS_LEGACY)
    tolerancia_sobrestock: Fraction = Fraction(1, 4)
    meses_inventario_muerto: int = 6
    mes_en_curso: Optional[MesEnCurso] = None


@dataclass(frozen=True)
class AjustesPrueba:
    """Sólo tests (nivel A1): divisor por referencia y orden explícito.

    Ningún camino de producción lo recibe (lo verifica S8a). Las claves son
    códigos de referencia: `divisor_por_referencia` reemplaza el divisor de N
    de esa referencia (el /18 de la plantilla) y `orden_explicito` es el
    orden físico del Excel, que gobierna el desempate del ABC.
    """

    divisor_por_referencia: Optional[Mapping[str, int]] = None
    orden_explicito: Optional[Sequence[str]] = None


@dataclass(frozen=True)
class Advertencia:
    """Aviso de la sucursal: código A-CORRIDA-nnn y mensaje en español."""

    codigo: str
    mensaje: str


@dataclass(frozen=True)
class LineaPedido:
    """Una línea del pedido: los insumos crudos más todo lo calculado.

    Los valores son `Fraction` exactas; se cuantizan sólo al persistir.
    `peso` y `acumulado` son nulos cuando la suma de N no es positiva, y
    `cobertura_final`/`cobertura_actual` cuando N = 0.
    `venta_m0_proyectada` es nula salvo con el mes en curso PONDERADO.
    """

    entrada: EntradaReferencia
    n: Fraction
    k_perdida: Fraction
    l_ultimo_mes: Fraction
    m_promedio: Fraction
    peso: Optional[Fraction]
    acumulado: Optional[Fraction]
    orden_abc: int
    clase_abc: str
    clase_fms: str
    clase: str
    meses_con_venta: int
    cobertura: Fraction
    inventario_efectivo: Fraction
    stock_objetivo: Fraction
    pedido: Fraction
    valor_pedido: Fraction
    cobertura_final: Optional[Fraction]
    cobertura_actual: Optional[Fraction]
    punto_minimo: Fraction
    punto_maximo: Fraction
    estado_quiebre: str
    advertencias: tuple[str, ...] = ()
    venta_m0_proyectada: Optional[Fraction] = None


@dataclass(frozen=True)
class NodoMaestro:
    """Una referencia del maestro de sustitución (sólo las que interesan).

    Entran las inactivas y las que declaran `sustituida_por`; una referencia
    ausente del maestro es una activa sin sustituta, o sea una FINAL.
    """

    referencia_id: UUID
    activa: bool
    sustituida_por: Optional[UUID] = None


@dataclass(frozen=True)
class Resolucion:
    """Destino de una referencia tras seguir su cadena de sustitución.

    `motivo` es `None` para una FINAL (`final_id` es ella misma),
    `MOTIVO_SUSTITUIDA` con la sustituta activa final en `final_id`, o
    `MOTIVO_SIN_REEMPLAZO` con `final_id` nulo. `ciclo` marca las cadenas
    cíclicas o demasiado largas (A-CORRIDA-103). `cadena` va desde la
    referencia hasta el último nodo visitado.
    """

    referencia_id: UUID
    final_id: Optional[UUID]
    motivo: Optional[str]
    cadena: tuple[UUID, ...]
    ciclo: bool = False


@dataclass(frozen=True)
class LineaExcluida:
    """Referencia que sale del pedido, con sus insumos crudos (sin cálculo).

    `sustituta_final_*` son nulos cuando no hay reemplazo ("inactiva sin
    reemplazo, revisar"); si no, es "demanda transferida a X".
    """

    entrada: EntradaReferencia
    motivo: str
    sustituta_final_id: Optional[UUID]
    sustituta_final_codigo: Optional[str]
