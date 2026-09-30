"""
Motored Pedidos — modelo `corrida_linea` (sdd/motored-pedidos-motor, Fase 3
"Motor", S4a; design ADR-3, ADR-4, ADR-12).

Una fila por referencia y sucursal de una corrida. Es ANCHA a propósito: las
entradas crudas propias (ventas y pérdidas por mes, V, W, X, Z, U, T) viven
junto a las salidas del motor, así el reproceso puro y la comparación de
entradas del Nivel B no necesitan joins ni JSON. Las referencias excluidas
(`SUSTITUIDA`, `INACTIVA_SIN_REEMPLAZO`) viven en la MISMA tabla, con
`motivo_exclusion` y sin N ni clase (spec §6.11.3).

Nomenclatura de meses: `m6..m1` son los seis meses cerrados (m6 el más
antiguo, peso 1; m1 el más reciente, peso 6); `m0` es el mes en curso y solo
se llena cuando el modo efectivo es PONDERADO (ADR-12).

Escalas de almacenamiento (ADR-1): entradas `numeric(14,2)` (mismas que las
fuentes, sin pérdida); N/K/L/M/SS/mínimos/máximos y `venta_m0_proyectada`
`numeric(18,6)`; pesos `numeric(14,10)`; coberturas `numeric(12,6)`;
pedido `numeric(14,2)`; valor `numeric(16,2)`. El motor calcula en
fracciones exactas y cuantiza SOLO al persistir.

`ultima_fecha_entrada` queda siempre NULL en F3 (reservada). `pedido_final`
es igual a `pedido_sugerido` en F3: ningún endpoint lo edita.
"""
from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from app.motored.database import MotoredBase


def _entrada(nullable=False):
    return Column(Numeric(14, 2), nullable=nullable)


def _calculo(nullable=True):
    return Column(Numeric(18, 6), nullable=nullable)


class CorridaLinea(MotoredBase):
    __tablename__ = "corrida_linea"
    __table_args__ = (
        UniqueConstraint(
            "corrida_id", "sucursal_id", "referencia_id",
            name="uq_corrida_linea_corrida_sucursal_referencia",
        ),
        Index(
            "ix_corrida_linea_corrida_sucursal_orden_abc",
            "corrida_id", "sucursal_id", "orden_abc",
        ),
        Index(
            "ix_corrida_linea_corrida_referencia",
            "corrida_id", "referencia_id",
        ),
        Index(
            "ix_corrida_linea_corrida_estado_quiebre",
            "corrida_id", "estado_quiebre",
        ),
    )

    id = Column(BigInteger, Identity(), primary_key=True)
    corrida_id = Column(
        UUID(as_uuid=True),
        ForeignKey("corrida.id", ondelete="CASCADE"),
        nullable=False,
    )
    sucursal_id = Column(
        UUID(as_uuid=True), ForeignKey("sucursal.id"), nullable=False,
    )
    referencia_id = Column(
        UUID(as_uuid=True), ForeignKey("referencia.id"), nullable=False,
    )
    codigo_referencia = Column(String(100), nullable=False)
    nombre_parte = Column(String(255), nullable=True)
    linea_comercial = Column(String(60), nullable=True)
    ultima_fecha_entrada = Column(Date, nullable=True)

    # --- Entradas crudas propias: meses cerrados m6..m1 -----------------
    venta_m6 = _entrada()
    venta_m5 = _entrada()
    venta_m4 = _entrada()
    venta_m3 = _entrada()
    venta_m2 = _entrada()
    venta_m1 = _entrada()
    perdida_m6 = _entrada()
    perdida_m5 = _entrada()
    perdida_m4 = _entrada()
    perdida_m3 = _entrada()
    perdida_m2 = _entrada()
    perdida_m1 = _entrada()
    # --- Mes en curso: NULL salvo modo efectivo PONDERADO ----------------
    venta_m0 = _entrada(nullable=True)
    perdida_m0 = _entrada(nullable=True)
    # --- Otras entradas: T, U, V, W, X, Z --------------------------------
    precio = _entrada(nullable=True)
    unidad_empaque = Column(Integer, nullable=False)
    inventario = _entrada()
    transito = _entrada()
    backorder = _entrada()
    ajuste = _entrada()

    # --- Salidas: K, L, M, N y proyección de m0 --------------------------
    demanda_perdida = _calculo()
    demanda_perdida_mensualizada = _calculo()
    demanda_prom_simple = _calculo()
    venta_m0_proyectada = _calculo()
    demanda_ponderada = _calculo()
    # --- Clasificación ---------------------------------------------------
    peso_pct = Column(Numeric(14, 10), nullable=True)
    peso_acum_pct = Column(Numeric(14, 10), nullable=True)
    orden_abc = Column(Integer, nullable=True)
    clase_abc = Column(String(1), nullable=True)
    clase_fms = Column(String(1), nullable=True)
    clase = Column(String(2), nullable=True)
    meses_con_venta = Column(SmallInteger, nullable=True)
    # --- Cobertura, stock objetivo y pedido ------------------------------
    meses_cobertura = Column(Numeric(12, 6), nullable=True)
    inventario_final = _entrada(nullable=True)
    y_recibido = _entrada(nullable=True)
    stock_objetivo = _calculo()
    pedido_sugerido = Column(Numeric(14, 2), nullable=True)
    pedido_final = Column(Numeric(14, 2), nullable=True)
    valor_pedido = Column(Numeric(16, 2), nullable=True)
    cobertura_final = Column(Numeric(12, 6), nullable=True)
    cobertura_actual = Column(Numeric(12, 6), nullable=True)
    punto_minimo = _calculo()
    punto_maximo = _calculo()
    estado_quiebre = Column(String(24), nullable=True)

    # --- Exclusión y consolidación de sustitutas -------------------------
    motivo_exclusion = Column(String(30), nullable=True)
    sustituta_final_id = Column(
        UUID(as_uuid=True), ForeignKey("referencia.id"), nullable=True,
    )
    banderas = Column(
        ARRAY(String(30)), nullable=False, server_default=text("'{}'"),
    )
    detalle_consolidacion = Column(JSONB, nullable=True)
