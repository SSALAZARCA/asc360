"""
Motored Pedidos — Fase 2 "Ingesta", Phase 9 "Adapter + API" (PR9), task 9.2
(sdd/motored-pedidos-ingesta; spec "parametro_metodologia vigente-by-clave
read path", proposal "`parametro_metodologia` READ path -- first consumer
ever").

`services/parametros.py::resolver()` is the FIRST real reader of
`parametro_metodologia` (Fase 1/Phase 3 built only the table+writer,
`registrar_cambio`/`obtener_vigente` -- see `test_parametros_versioning.py`
-- with zero callers anywhere in the engine). It wraps `obtener_vigente`
with a coded default fallback, logged whenever no vigente row exists for a
`clave` (spec: "the fact is recorded in the load log, so a silent default
never looks like a configured choice" -- persisting THAT fact into a
specific `carga_archivo.log` is `orquestador.py`'s job, since only the
caller knows which load is asking; this module logs via the standard
`logging` module, which is the only log surface a clave-agnostic pure
resolver can own).

Verify-report WARNING #2 follow-up (sdd/motored-pedidos-ingesta): `resolver()`
and every `resolver_*` wrapper now return a `ResolverResultado(valor,
fue_default)` `NamedTuple` instead of a bare value -- `fue_default` is what
`orquestador.py` threads into `carga.log["parametros_default_usados"]`. Every
test below that used to do `valor = await resolver(...)` now unpacks both
fields.
"""
import datetime
import logging
import uuid

from sqlalchemy.dialects import postgresql

from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import parametros
from tests.motored.conftest import FakeAsyncSession

FECHA = datetime.date(2026, 9, 15)


class TestResolverGenerico:
    async def test_returns_configured_value_when_a_vigente_row_exists(self):
        fila = ParametroMetodologia(
            id=uuid.uuid4(), clave="tipos_inventario_incluidos",
            valor=["0002 - REPUESTOS", "0003 - ACCESORIOS"], vigente_desde=FECHA,
        )
        db = FakeAsyncSession(execute_queue=[[fila]])

        valor, fue_default = await parametros.resolver(
            db, "tipos_inventario_incluidos", FECHA, default=["0002 - REPUESTOS"]
        )

        assert valor == ["0002 - REPUESTOS", "0003 - ACCESORIOS"]
        assert fue_default is False

    async def test_falls_back_to_the_caller_supplied_default_when_no_row_exists(self):
        db = FakeAsyncSession(execute_queue=[[]])

        valor, fue_default = await parametros.resolver(
            db, "clave_inexistente", FECHA, default="valor_default"
        )

        assert valor == "valor_default"
        assert fue_default is True

    async def test_default_fallback_is_logged(self, caplog):
        db = FakeAsyncSession(execute_queue=[[]])

        with caplog.at_level(logging.WARNING, logger="app.motored.services.parametros"):
            await parametros.resolver(db, "clave_inexistente", FECHA, default="valor_default")

        assert any("clave_inexistente" in record.message for record in caplog.records)

    async def test_configured_value_does_not_log_a_default_fallback(self, caplog):
        fila = ParametroMetodologia(
            id=uuid.uuid4(), clave="dias_ventana_ingresos", valor=60, vigente_desde=FECHA,
        )
        db = FakeAsyncSession(execute_queue=[[fila]])

        with caplog.at_level(logging.WARNING, logger="app.motored.services.parametros"):
            await parametros.resolver(db, "dias_ventana_ingresos", FECHA, default=45)

        assert caplog.records == []


class TestClavesDeFase2ConDefaultCodificado:
    """Los 5 claves que Fase 2 realmente consume (spec §6.10 + proposal
    "parametro_metodologia READ path"). `prefijos_documento_devolucion`
    NO está acá a propósito -- dropped per Decision #2 del proposal (el
    signed `Cantidad inv.` se suma tal cual, sin clasificación de
    devolución)."""

    async def test_tipos_inventario_incluidos_default(self):
        db = FakeAsyncSession(execute_queue=[[]])

        valor, fue_default = await parametros.resolver_tipos_inventario_incluidos(db, FECHA)

        assert valor == ["0002 - REPUESTOS", "IRPTOSYACC", "IVNLUBGR", "0003 - OTROS"]
        assert fue_default is True

    async def test_estados_backorder_vigentes_default(self):
        db = FakeAsyncSession(execute_queue=[[]])

        valor, fue_default = await parametros.resolver_estados_backorder_vigentes(db, FECHA)

        assert valor == ["BACKORDER"]
        assert fue_default is True

    async def test_dias_ventana_ingresos_default(self):
        db = FakeAsyncSession(execute_queue=[[]])

        valor, fue_default = await parametros.resolver_dias_ventana_ingresos(db, FECHA)

        assert valor == 45
        assert fue_default is True

    async def test_tolerancia_ingreso_pct_default(self):
        db = FakeAsyncSession(execute_queue=[[]])

        valor, fue_default = await parametros.resolver_tolerancia_ingreso_pct(db, FECHA)

        assert valor == 2.0
        assert fue_default is True

    async def test_crear_referencias_desconocidas_default(self):
        """Sin default explícito en la especificación fuente (verificado por
        búsqueda directa contra `ESPECIFICACION_MOTORED_PEDIDOS.md` -- no
        hay ninguna fila para esta clave en la tabla §6.10 ni en ningún otro
        lugar). Se elige `False` (no autocrear) como el default más seguro:
        una referencia desconocida sin autocreación cae a `carga_error` con
        una acción explícita "crear como OTROS" -- nunca un side-effect de
        escritura silencioso -- consistente con el resto de defaults "off"
        de esta fase (p.ej. `MOTORED_RETENCION_ENABLED=False`). Ver
        apply-progress-phase9a para el detalle de esta decisión."""
        db = FakeAsyncSession(execute_queue=[[]])

        valor, fue_default = await parametros.resolver_crear_referencias_desconocidas(db, FECHA)

        assert valor is False
        assert fue_default is True

    async def test_configured_value_overrides_every_default(self):
        fila = ParametroMetodologia(
            id=uuid.uuid4(), clave="estados_backorder_vigentes",
            valor=["BACKORDER", "PENDIENTE_PARCIAL"], vigente_desde=FECHA,
        )
        db = FakeAsyncSession(execute_queue=[[fila]])

        valor, fue_default = await parametros.resolver_estados_backorder_vigentes(db, FECHA)

        assert valor == ["BACKORDER", "PENDIENTE_PARCIAL"]
        assert fue_default is False


# ---------------------------------------------------------------------------
# S4b (sdd/motored-pedidos-motor, ADR-7): alcance por sucursal.
# ---------------------------------------------------------------------------


def _sql(statement) -> str:
    compilado = statement.compile(dialect=postgresql.dialect())
    return " ".join(str(compilado).split())


def _fila(clave, valor, desde, sucursal_id=None, creada=None):
    return ParametroMetodologia(
        id=uuid.uuid4(), clave=clave, valor=valor, vigente_desde=desde,
        sucursal_id=sucursal_id, created_at=creada,
    )


class TestLecturaGlobalSigueIgual:
    async def test_obtener_vigente_only_reads_global_rows(self):
        db = FakeAsyncSession(execute_queue=[[]])

        await parametros.obtener_vigente(db, "dias_seguridad", FECHA)

        assert "sucursal_id IS NULL" in _sql(db.executed_statements[0])

    async def test_obtener_vigente_breaks_ties_by_created_at_desc(self):
        db = FakeAsyncSession(execute_queue=[[]])

        await parametros.obtener_vigente(db, "dias_seguridad", FECHA)

        orden = _sql(db.executed_statements[0]).split("ORDER BY")[1]
        assert "vigente_desde DESC" in orden
        assert "created_at DESC" in orden
        assert orden.index("vigente_desde") < orden.index("created_at")

    async def test_registrar_cambio_can_scope_a_row_to_a_sucursal(self):
        sucursal = uuid.uuid4()
        db = FakeAsyncSession()

        nueva = await parametros.registrar_cambio(
            db, "dias_entre_pedidos", 7, FECHA, sucursal_id=sucursal,
        )

        assert nueva.sucursal_id == sucursal

    async def test_registrar_cambio_defaults_to_the_global_scope(self):
        db = FakeAsyncSession()

        nueva = await parametros.registrar_cambio(
            db, "dias_entre_pedidos", 30, FECHA,
        )

        assert nueva.sucursal_id is None


class TestObtenerVigentesMotor:
    async def test_reads_every_key_with_a_single_distinct_on_query(self):
        db = FakeAsyncSession(execute_queue=[[]])

        await parametros.obtener_vigentes_motor(
            db, ["dias_entre_pedidos", "k_fms", "umbral_f"], FECHA,
        )

        assert len(db.executed_statements) == 1
        sql = _sql(db.executed_statements[0])
        assert "DISTINCT ON" in sql
        assert "parametro_metodologia.clave" in sql.split("DISTINCT ON")[1]

    async def test_query_filters_versions_effective_at_the_corte(self):
        db = FakeAsyncSession(execute_queue=[[]])

        await parametros.obtener_vigentes_motor(db, ["k_fms"], FECHA)

        compilado = db.executed_statements[0].compile(
            dialect=postgresql.dialect())
        assert FECHA in compilado.params.values()
        assert "vigente_desde <=" in _sql(db.executed_statements[0])

    async def test_query_orders_newest_version_and_created_at_first(self):
        db = FakeAsyncSession(execute_queue=[[]])

        await parametros.obtener_vigentes_motor(db, ["k_fms"], FECHA)

        orden = _sql(db.executed_statements[0]).split("ORDER BY")[1]
        assert "vigente_desde DESC" in orden
        assert "created_at DESC" in orden

    async def test_sucursal_row_wins_over_global_and_default(self):
        sucursal = uuid.uuid4()
        filas = [
            _fila("dias_entre_pedidos", 15, FECHA),
            _fila("dias_entre_pedidos", 7, FECHA, sucursal),
        ]
        db = FakeAsyncSession(execute_queue=[filas])

        vigentes = await parametros.obtener_vigentes_motor(
            db, ["dias_entre_pedidos"], FECHA)

        propia = vigentes.resolver("dias_entre_pedidos", sucursal)
        ajena = vigentes.resolver("dias_entre_pedidos", uuid.uuid4())
        assert (propia.valor, propia.fuente) == (7, "SUCURSAL")
        assert (ajena.valor, ajena.fuente) == (15, "GLOBAL")

    async def test_falls_back_to_the_registry_default(self):
        db = FakeAsyncSession(execute_queue=[[]])

        vigentes = await parametros.obtener_vigentes_motor(
            db, ["dias_entre_pedidos"], FECHA)

        r = vigentes.resolver("dias_entre_pedidos", uuid.uuid4())
        assert (r.valor, r.fuente) == (30, "DEFAULT")
        assert r.parametro_id is None and r.vigente_desde is None

    async def test_resolution_carries_row_id_and_vigente_desde(self):
        fila = _fila("k_fms", {"F": "4", "M": "2", "S": "1"}, FECHA)
        db = FakeAsyncSession(execute_queue=[[fila]])

        vigentes = await parametros.obtener_vigentes_motor(
            db, ["k_fms"], FECHA)

        r = vigentes.resolver("k_fms")
        assert r.parametro_id == fila.id
        assert r.vigente_desde == FECHA
        assert r.fuente == "GLOBAL"

    async def test_override_wins_over_sucursal_and_global(self):
        sucursal = uuid.uuid4()
        filas = [
            _fila("dias_entre_pedidos", 15, FECHA),
            _fila("dias_entre_pedidos", 7, FECHA, sucursal),
        ]
        db = FakeAsyncSession(execute_queue=[filas])

        vigentes = await parametros.obtener_vigentes_motor(
            db, ["dias_entre_pedidos"], FECHA,
            overrides={"dias_entre_pedidos": 21},
        )

        r = vigentes.resolver("dias_entre_pedidos", sucursal)
        assert (r.valor, r.fuente) == (21, "OVERRIDE")
        assert filas[1].valor == 7 and filas[0].valor == 15

    async def test_unknown_stored_keys_never_break_a_read(self):
        """Una clave guardada que el registro no conoce se lee igual."""
        fila = _fila("clave_historica_rara", "x", FECHA)
        db = FakeAsyncSession(execute_queue=[[fila]])

        vigentes = await parametros.obtener_vigentes_motor(
            db, ["clave_historica_rara"], FECHA)

        r = vigentes.resolver("clave_historica_rara")
        assert (r.valor, r.fuente) == ("x", "GLOBAL")

    async def test_unknown_key_without_a_row_has_no_default(self):
        db = FakeAsyncSession(execute_queue=[[]])

        vigentes = await parametros.obtener_vigentes_motor(
            db, ["clave_historica_rara"], FECHA)

        r = vigentes.resolver("clave_historica_rara")
        assert (r.valor, r.fuente) == (None, "DEFAULT")
