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
    """Configuración efectiva del mes en curso (M0). La usa S3b."""

    modo: ModoMesEnCurso
    d: int
    D: int
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

    Ningún camino de producción lo recibe (lo verifica S8a). En S1 es un
    contenedor sin efecto; el motor ensamblado (S2) lo aplicará.
    """

    divisor_por_referencia: Optional[Mapping[str, int]] = None
    orden_explicito: Optional[Sequence[str]] = None
