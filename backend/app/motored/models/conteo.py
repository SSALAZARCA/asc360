"""
Motored inventory counts -- the `conteo` header (odd/motored-conteos-
inventario, WU2; design §4.1, §5.1, ADR-1, ADR-9).

One row per physical store count. Owner overrides on top of the design:

- the count is per STORE (`sucursal_id`); it is never rolled up to the
  store's `principal_id`;
- `lider_id` is the assigned LIDER_INVENTARIOS, required for TOTAL counts
  (`ck_conteo_lider_si_total`). Only that leader (or ADMIN) acts on the
  count; the scoping itself lives in the services;
- the money thresholds are copied from Configuración at Iniciar (ADR-9),
  so an edit mid-count never changes which referencias need a reconteo;
- `es_prueba` (odd/tasks/motored-conteo-prueba.md) marks an ADMIN-only
  test count: only ADMIN sees it, it is left out of the one-open-TOTAL
  index and of every cross-count aggregate, and it may be hard-deleted.

`tipo` keeps 'SELECTIVO' (stage 3) so that stage needs no migration for
it. Enumerations are `String` + CHECK, never Postgres enums.
"""
import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index,
    Integer, Numeric, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.motored.database import MotoredBase

TIPOS = ("TOTAL", "SELECTIVO")
ESTADOS = (
    "PROGRAMADO", "EN_CONTEO", "EN_RECONTEO", "CERRADO", "ANULADO")
ESTADOS_ABIERTOS = ("EN_CONTEO", "EN_RECONTEO")
ORIGENES = ("MANUAL", "AUTOMATICO")
INDICE_TOTAL_ABIERTO = "uq_conteo_total_abierto"


def lista_sql(valores):
    """`('A','B')` for a CHECK ... IN clause."""
    return "(" + ", ".join(f"'{v}'" for v in valores) + ")"


def _usuario_fk():
    return Column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True)


def _conteo_fk():
    return Column(
        UUID(as_uuid=True),
        ForeignKey("conteo.id", ondelete="RESTRICT"),
        nullable=True,
    )


class Conteo(MotoredBase):
    __tablename__ = "conteo"
    __table_args__ = (
        CheckConstraint(f"tipo IN {lista_sql(TIPOS)}", name="ck_conteo_tipo"),
        CheckConstraint(
            f"estado IN {lista_sql(ESTADOS)}", name="ck_conteo_estado"),
        CheckConstraint(
            f"origen IN {lista_sql(ORIGENES)}", name="ck_conteo_origen"),
        CheckConstraint(
            "tipo <> 'TOTAL' OR lider_id IS NOT NULL",
            name="ck_conteo_lider_si_total"),
        CheckConstraint(
            "estado IN ('PROGRAMADO', 'ANULADO') "
            "OR snapshot_tomado_en IS NOT NULL",
            name="ck_conteo_snapshot_si_iniciado"),
        CheckConstraint(
            "estado IN ('PROGRAMADO', 'ANULADO') OR ("
            "umbral_reconteo_pesos IS NOT NULL "
            "AND umbral_critico_pesos IS NOT NULL)",
            name="ck_conteo_umbrales_si_iniciado"),
        CheckConstraint(
            "tipo = 'TOTAL' OR enlace_slug IS NULL",
            name="ck_conteo_slug_solo_total"),
        UniqueConstraint("enlace_slug", name="uq_conteo_enlace_slug"),
        Index(
            INDICE_TOTAL_ABIERTO, "sucursal_id", unique=True,
            postgresql_where=text(
                "tipo = 'TOTAL' AND estado IN ('EN_CONTEO', 'EN_RECONTEO') "
                "AND NOT es_prueba"),
        ),
        Index(
            "uq_conteo_selectivo_semana", "sucursal_id", "semana_iso",
            unique=True,
            postgresql_where=text(
                "tipo = 'SELECTIVO' AND origen = 'AUTOMATICO' "
                "AND verifica_conteo_id IS NULL "
                "AND arrastra_conteo_id IS NULL AND estado <> 'ANULADO'"),
        ),
        Index("ix_conteo_estado_fecha", "estado", "fecha_programada"),
        Index(
            "ix_conteo_sucursal_cerrado",
            "sucursal_id", text("cerrado_en DESC"),
        ),
        Index("ix_conteo_lider", "lider_id", "fecha_programada"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo = Column(String(10), nullable=False, default="TOTAL")
    sucursal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sucursal.id", ondelete="RESTRICT"),
        nullable=False,
    )
    lider_id = Column(
        UUID(as_uuid=True),
        ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=True,
    )
    estado = Column(String(16), nullable=False, default="PROGRAMADO")
    fecha_programada = Column(Date, nullable=False)
    origen = Column(String(12), nullable=False, default="MANUAL")
    semana_iso = Column(String(8), nullable=True)
    es_prueba = Column(
        Boolean, nullable=False, default=False,
        server_default=text("false"))
    verifica_conteo_id = _conteo_fk()
    arrastra_conteo_id = _conteo_fk()

    creado_por = _usuario_fk()
    iniciado_por = _usuario_fk()
    cerrado_por = _usuario_fk()
    anulado_por = _usuario_fk()
    motivo_anulacion = Column(Text, nullable=True)
    motivo_cierre_forzado = Column(Text, nullable=True)

    snapshot_carga_id = Column(
        UUID(as_uuid=True),
        ForeignKey("carga_archivo.id", ondelete="SET NULL"),
        nullable=True,
    )
    snapshot_fecha_corte = Column(Date, nullable=True)
    snapshot_aplicado_en = Column(DateTime(timezone=True), nullable=True)
    snapshot_tomado_en = Column(DateTime(timezone=True), nullable=True)
    snapshot_advertencias = Column(JSONB, nullable=True)
    umbral_reconteo_pesos = Column(Numeric(16, 2), nullable=True)
    umbral_critico_pesos = Column(Numeric(16, 2), nullable=True)

    enlace_slug = Column(String(16), nullable=True)
    codigo_hash = Column(String(64), nullable=True)
    codigo_rotado_en = Column(DateTime(timezone=True), nullable=True)
    acceso_fallidos_hora = Column(
        Integer, nullable=False, default=0, server_default=text("0"))
    acceso_ventana_inicio = Column(DateTime(timezone=True), nullable=True)

    iniciado_en = Column(DateTime(timezone=True), nullable=True)
    ronda_terminada_en = Column(DateTime(timezone=True), nullable=True)
    cerrado_en = Column(DateTime(timezone=True), nullable=True)
    anulado_en = Column(DateTime(timezone=True), nullable=True)

    refs_universo = Column(Integer, nullable=True)
    refs_exactas = Column(Integer, nullable=True)
    exactitud_pct = Column(Numeric(6, 2), nullable=True)
    valor_sistema = Column(Numeric(18, 2), nullable=True)
    valor_diferencia_neta = Column(Numeric(18, 2), nullable=True)
    valor_diferencia_abs = Column(Numeric(18, 2), nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now())
