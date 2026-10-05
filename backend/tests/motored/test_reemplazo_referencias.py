"""
Motored `motored-referencia-identidad` (R2): la carga de referencias es un
REEMPLAZO COMPLETO -- el archivo es la verdad.

- Una celda opcional en blanco BORRA el valor guardado (nombre, linea,
  precios, sustituta, homologados); `unidad_empaque` en blanco queda en 1 con
  aviso, nunca 0.
- Las referencias del archivo quedan activas; las que vuelven se reactivan.
- R3: las activas que NO estan en el archivo (ausentes) se LISTAN, no se
  desactivan: siguen activas salvo las que el usuario elija en
  `codigos_inactivar` (subconjunto de las ausentes, recalculadas al aplicar;
  si no, 409). Nunca se borra nada.
- Un dry-run (`resumen_reemplazo`) cuenta crear/actualizar/mover/reactivar y
  los vinculos de sustituta quitados, lista TODAS las ausentes (resaltando las
  que vendieron en los ultimos 6 meses o tienen stock) y exige DOBLE
  confirmacion si lo elegido + las que quedan inactivas por sustituta pasan
  del 10% de las activas.
- Aplicar exige `confirmar_reemplazo`; recalcula el resumen y, si exige doble
  confirmacion y no vino, responde 409. Todo-o-nada en una transaccion.

`FakeAsyncSession` encola los resultados en el orden de las queries del
servicio: [todas las referencias], [todos los proveedores] y, solo si hay
referencias por desactivar, [ids con ventas 6m], [ultima fecha_corte],
[ids con stock].
"""
import datetime
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.motored.models.auditoria_maestro import AuditoriaMaestro
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.services import carga, kpi_resumen, reemplazo_referencias
from tests.motored.conftest import FakeAsyncSession


@pytest.fixture(autouse=True)
def _marcas_de_sucio(monkeypatch):
    """The KPI summaries' dirty flag (R7a) is spied on, not written: this suite's fake session
    has a fixed query queue. The SQL is covered in `pg_real/test_kpi_resumen_sucio_pg.py`."""
    marcas = []

    async def marcar(db):
        marcas.append(db)
        return True

    monkeypatch.setattr(kpi_resumen, "marcar_sucio_si_construido", marcar)
    return marcas

HMCL = Proveedor(id=uuid.uuid4(), codigo="HMCL", nombre="HMCL", es_principal=True)
OTRO = Proveedor(id=uuid.uuid4(), codigo="OTRO", nombre="Otro", es_principal=False)
HOY = datetime.date(2026, 10, 3)


def _ref(codigo, proveedor=HMCL, activa=True, **extra):
    campos = dict(nombre=None, linea_comercial=None, unidad_empaque=1, homologados=[])
    campos.update(extra)
    return Referencia(id=uuid.uuid4(), codigo=codigo, proveedor_id=proveedor.id, activa=activa, **campos)


def _fila(codigo, proveedor=HMCL, **extra):
    return {"codigo": codigo, "proveedor_codigo": proveedor.codigo, "proveedor_id": proveedor.id, **extra}


def _db(referencias, ventas=(), fecha_corte=None, con_stock=()):
    cola = [list(referencias), [HMCL, OTRO]]
    if any(r.activa for r in referencias):
        cola += [list(ventas), [fecha_corte], list(con_stock) if fecha_corte else []]
    return FakeAsyncSession(execute_queue=cola)


async def _plan(referencias, filas, **kw):
    db = _db(referencias, **kw)
    plan = await reemplazo_referencias.planificar(db, filas, hoy=HOY)
    return plan, db


async def _aplicar(referencias, filas, confirmar_reemplazo=True, confirmar_masiva=False,
                   codigos_inactivar=None, **kw):
    db = _db(referencias, **kw)
    resultado = await carga.procesar_carga(
        db, "referencia", filas,
        confirmar_reemplazo=confirmar_reemplazo, confirmar_inactivacion_masiva=confirmar_masiva,
        codigos_inactivar=codigos_inactivar)
    return resultado, db


# --- Una celda en blanco borra el valor guardado -----------------------------


async def test_una_celda_opcional_en_blanco_borra_el_valor_guardado():
    sustituta = _ref("SUST")
    existente = _ref("R-1", nombre="Vieja", linea_comercial="MOTOR", unidad_empaque=4,
                     precio_normal=Decimal("100"), precio_publico=Decimal("150"),
                     homologados=["Honda"], sustituida_por=sustituta.id, activa=False)

    resultado, _ = await _aplicar([existente, sustituta], [_fila("R-1"), _fila("SUST")])

    assert resultado.ok is True, resultado
    assert existente.nombre is None and existente.linea_comercial is None
    assert existente.precio_normal is None and existente.precio_publico is None
    assert existente.homologados == [] and existente.sustituida_por is None


async def test_un_valor_en_el_archivo_reemplaza_al_guardado():
    existente = _ref("R-1", nombre="Vieja", precio_normal=Decimal("100"))

    await _aplicar([existente], [_fila("R-1", nombre="Nueva", precio_normal=Decimal("120"),
                                       homologados=["Yamaha"], unidad_empaque=6)])

    assert existente.nombre == "Nueva" and existente.precio_normal == Decimal("120")
    assert existente.homologados == ["Yamaha"] and existente.unidad_empaque == 6


async def test_unidad_empaque_en_blanco_queda_en_1_con_aviso_nunca_0():
    existente = _ref("R-1", unidad_empaque=12)

    resultado, _ = await _aplicar([existente], [_fila("R-1")])

    assert existente.unidad_empaque == 1 and existente.unidad_empaque_advertencia is True
    assert any("unidad_empaque" in str(a) for a in resultado.advertencias)


async def test_una_referencia_nueva_con_unidad_empaque_en_blanco_se_crea_con_1_y_aviso():
    resultado, db = await _aplicar([_ref("OTRA")], [_fila("NUEVA")], confirmar_masiva=True)

    [creada] = db.added_of_type(Referencia)
    assert creada.codigo == "NUEVA" and creada.unidad_empaque == 1
    assert creada.unidad_empaque_advertencia is True
    assert any("unidad_empaque" in str(a) for a in resultado.advertencias)


async def test_las_columnas_requeridas_siguen_siendo_requeridas():
    resultado, db = await _aplicar([_ref("R-1")], [{"codigo": "R-1", "proveedor_codigo": ""}])

    assert resultado.ok is False and db.committed is False


# --- Activar / desactivar / reactivar ----------------------------------------


async def test_por_defecto_aplicar_no_desactiva_a_las_ausentes():
    en_archivo = _ref("A")
    ausente = _ref("B")
    vuelve = _ref("C", activa=False)

    resultado, db = await _aplicar([en_archivo, ausente, vuelve], [_fila("A"), _fila("C")])

    assert resultado.ok is True
    assert (en_archivo.activa, ausente.activa, vuelve.activa) == (True, True, True)
    assert db.committed is True
    acciones = {(a.entidad_id, a.accion) for a in db.added_of_type(AuditoriaMaestro)}
    assert (ausente.id, "deactivate") not in acciones and (vuelve.id, "reactivate") in acciones


async def test_una_lista_vacia_tampoco_desactiva_nada():
    ausente = _ref("B")

    await _aplicar([_ref("A"), ausente], [_fila("A")], codigos_inactivar=[])

    assert ausente.activa is True


async def test_solo_se_desactivan_los_codigos_elegidos_sin_borrar_nada():
    en_archivo, elegida, otra = _ref("A"), _ref("B"), _ref("C")

    resultado, db = await _aplicar([en_archivo, elegida, otra], [_fila("A")],
                                   codigos_inactivar=["B"], confirmar_masiva=True)

    assert resultado.ok is True
    assert (en_archivo.activa, elegida.activa, otra.activa) == (True, False, True)
    assert not any(type(s).__name__ == "Delete" for s in db.executed_statements)
    acciones = {(a.entidad_id, a.accion) for a in db.added_of_type(AuditoriaMaestro)}
    assert (elegida.id, "deactivate") in acciones and (otra.id, "deactivate") not in acciones


async def test_un_codigo_elegido_que_no_es_ausente_es_409_y_no_se_aplica_nada():
    en_archivo, ausente, inactiva = _ref("A", nombre="Original"), _ref("B"), _ref("I", activa=False)
    db = _db([en_archivo, ausente, inactiva])

    with pytest.raises(HTTPException) as exc:
        await carga.procesar_carga(
            db, "referencia", [_fila("A", nombre="Nueva")], confirmar_reemplazo=True,
            codigos_inactivar=["B", "A", "I", "NOEXISTE"])

    assert exc.value.status_code == 409
    assert "A" in exc.value.detail and "NOEXISTE" in exc.value.detail and "ausente" in exc.value.detail.lower()
    assert en_archivo.nombre == "Original" and ausente.activa is True and db.committed is False


async def test_los_codigos_elegidos_se_recortan_y_no_se_cuentan_dos_veces():
    ausente = _ref("B")

    resultado, _ = await _aplicar([_ref("A"), ausente], [_fila("A")], codigos_inactivar=[" B ", "B"],
                                  confirmar_masiva=True)

    assert ausente.activa is False and resultado.resumen_reemplazo.seleccionadas == 1


async def test_una_inactiva_ausente_del_archivo_no_cambia():
    inactiva = _ref("VIEJA", activa=False)

    plan, _ = await _plan([_ref("A"), inactiva], [_fila("A")])

    assert inactiva not in plan.ausentes and inactiva not in plan.reactivar


async def test_una_referencia_con_sustituta_en_el_archivo_queda_inactiva():
    vieja, nueva = _ref("VIEJA"), _ref("NUEVA")
    filas = [_fila("VIEJA", **{"_sustituta_codigo_en_archivo": "NUEVA"}), _fila("NUEVA")]

    resultado, _ = await _aplicar([vieja, nueva], filas, confirmar_masiva=True)

    assert resultado.ok is True
    assert vieja.sustituida_por == nueva.id and vieja.activa is False and nueva.activa is True


async def test_agrega_las_referencias_nuevas_sin_duplicar_las_existentes():
    existente = _ref("A")

    resultado, db = await _aplicar([existente], [_fila("A"), _fila("NUEVA", OTRO)])

    assert resultado.insertados == 1
    [creada] = db.added_of_type(Referencia)
    assert creada.codigo == "NUEVA" and creada.proveedor_id == OTRO.id and creada.activa is True


# --- Mover de proveedor ---------------------------------------------------------


async def test_cambiar_el_proveedor_mueve_la_referencia_y_conserva_el_id():
    existente = _ref("A", HMCL)
    id_original = existente.id

    resultado, db = await _aplicar([existente], [_fila("A", OTRO)])

    assert existente.id == id_original and existente.proveedor_id == OTRO.id
    assert db.added_of_type(Referencia) == [] and resultado.insertados == 0


async def test_mover_quita_el_vinculo_de_una_ausente_que_la_tenia_de_sustituta():
    movida = _ref("NUEVA", HMCL)
    ausente = _ref("VIEJA", HMCL, activa=False, sustituida_por=movida.id)

    resultado, _ = await _aplicar([movida, ausente], [_fila("NUEVA", OTRO)], confirmar_masiva=True)

    assert ausente.sustituida_por is None
    resumen = resultado.resumen_reemplazo
    assert resumen.vinculos_sustituta_limpiados.total == 1
    assert resumen.vinculos_sustituta_limpiados.muestra[0]["codigo"] == "VIEJA"


async def test_mover_un_grupo_enlazado_al_mismo_proveedor_conserva_el_vinculo_sin_aviso():
    # El plan usa el proveedor FINAL de cada fila del archivo: A y B se mueven
    # juntas a OTRO y B.sustituida_por = A (repetida en el archivo) -> se mantiene.
    a, b = _ref("A", HMCL), _ref("B", HMCL, activa=False)
    b.sustituida_por = a.id
    filas = [_fila("A", OTRO), _fila("B", OTRO, **{"_sustituta_codigo_en_archivo": "A"})]

    resultado, _ = await _aplicar([a, b], filas, confirmar_masiva=True)

    assert resultado.ok is True
    assert (a.proveedor_id, b.proveedor_id) == (OTRO.id, OTRO.id)
    assert b.sustituida_por == a.id
    assert resultado.resumen_reemplazo.vinculos_sustituta_limpiados.total == 0


async def test_mover_un_grupo_enlazado_con_la_sustituta_en_blanco_limpia_el_vinculo():
    # "El archivo es la verdad": la celda en blanco borra la sustituta. No es un
    # vinculo cruzado (no hay aviso): lo borra el reemplazo, y queda en `actualizar`.
    a, b = _ref("A", HMCL), _ref("B", HMCL, activa=False)
    b.sustituida_por = a.id

    resultado, _ = await _aplicar([a, b], [_fila("A", OTRO), _fila("B", OTRO)], confirmar_masiva=True)

    assert resultado.ok is True
    assert b.sustituida_por is None
    assert resultado.resumen_reemplazo.vinculos_sustituta_limpiados.total == 0


async def test_las_activas_que_quedan_inactivas_por_sustituta_cuentan_para_el_umbral():
    # 20 activas; 1 ausente ELEGIDA (5%) + 2 que ganan sustituta (10%) = 15% > 10%.
    referencias = [_ref(f"R-{i}") for i in range(20)]
    filas = [_fila(r.codigo) for r in referencias[1:]]
    filas[0] = _fila("R-1", **{"_sustituta_codigo_en_archivo": "R-5"})
    filas[1] = _fila("R-2", **{"_sustituta_codigo_en_archivo": "R-5"})

    plan, _ = await _plan(referencias, filas)
    sin_elegir = reemplazo_referencias.construir_resumen(plan)
    resumen = reemplazo_referencias.construir_resumen(plan, ["R-0"])

    assert resumen.ausentes.total == 1
    assert resumen.inactivar_por_sustituta.total == 2
    assert {m["codigo"] for m in resumen.inactivar_por_sustituta.muestra} == {"R-1", "R-2"}
    assert sin_elegir.pct_inactivar == pytest.approx(2 / 20) and sin_elegir.requiere_doble_confirmacion is False
    assert resumen.pct_inactivar == pytest.approx(3 / 20)
    assert resumen.pct_inactivar_si_todas == pytest.approx(3 / 20)
    assert resumen.requiere_doble_confirmacion is True


async def test_aplicar_con_inactivas_por_sustituta_sobre_el_umbral_sin_doble_confirmacion_es_409():
    referencias = [_ref(f"R-{i}") for i in range(20)]
    filas = [_fila(r.codigo) for r in referencias]
    for i in range(3):
        filas[i] = _fila(f"R-{i}", **{"_sustituta_codigo_en_archivo": "R-10"})

    with pytest.raises(HTTPException) as exc:
        await _aplicar(referencias, filas)

    assert exc.value.status_code == 409


# --- Errores de fila: todo o nada ------------------------------------------------


async def test_un_codigo_que_solo_difiere_en_mayusculas_de_uno_existente_es_error_de_fila():
    existente = _ref("AB-1")

    plan, _ = await _plan([existente], [_fila("ab-1")])

    assert [e["fila"] for e in plan.errores] == [1]
    assert "AB-1" in plan.errores[0]["motivo"]


async def test_un_error_de_fila_no_escribe_nada():
    existente = _ref("AB-1", nombre="Original")

    resultado, db = await _aplicar([existente], [_fila("OK"), _fila("ab-1")], confirmar_masiva=True)

    assert resultado.ok is False and resultado.errores[0].fila == 2
    assert existente.nombre == "Original" and existente.activa is True
    assert db.added == [] and db.committed is False


# --- Resumen (dry-run) -----------------------------------------------------------


async def test_el_resumen_cuenta_crear_actualizar_mover_inactivar_y_reactivar():
    igual = _ref("IGUAL", nombre="N")
    cambia = _ref("CAMBIA", nombre="Vieja")
    se_mueve = _ref("MUEVE", HMCL)
    se_va = _ref("SEVA")
    vuelve = _ref("VUELVE", activa=False)
    filas = [_fila("IGUAL", nombre="N"), _fila("CAMBIA", nombre="Nueva"), _fila("MUEVE", OTRO),
             _fila("NUEVA"), _fila("VUELVE")]

    plan, _ = await _plan([igual, cambia, se_mueve, se_va, vuelve], filas)
    resumen = reemplazo_referencias.construir_resumen(plan)

    assert resumen.total_archivo == 5
    assert resumen.crear.total == 1 and resumen.crear.muestra[0]["codigo"] == "NUEVA"
    assert resumen.actualizar.total == 1 and resumen.actualizar.muestra[0]["codigo"] == "CAMBIA"
    assert resumen.actualizar.muestra[0]["campos"] == ["nombre"]
    assert resumen.mover_proveedor.total == 1
    assert resumen.mover_proveedor.muestra[0] == {
        "codigo": "MUEVE", "proveedor_anterior": "HMCL", "proveedor_nuevo": "OTRO"}
    assert resumen.ausentes.total == 1 and resumen.ausentes.items[0]["codigo"] == "SEVA"
    assert resumen.seleccionadas == 0
    assert resumen.reactivar.total == 1 and resumen.reactivar.muestra[0]["codigo"] == "VUELVE"


async def test_una_fila_identica_a_lo_guardado_no_cuenta_como_actualizacion():
    existente = _ref("A", nombre="N", precio_normal=Decimal("100.00"), unidad_empaque=2,
                     homologados=["Honda"])

    plan, _ = await _plan([existente], [_fila("A", nombre="N", precio_normal=Decimal("100"),
                                              unidad_empaque=2, homologados=["Honda"])])

    assert reemplazo_referencias.construir_resumen(plan).actualizar.total == 0


async def test_borrar_un_valor_con_celda_en_blanco_cuenta_como_actualizacion():
    plan, _ = await _plan([_ref("A", nombre="N", unidad_empaque=1)], [_fila("A")])

    resumen = reemplazo_referencias.construir_resumen(plan)
    assert resumen.actualizar.muestra[0]["campos"] == ["nombre"]


async def test_inactivar_marca_las_que_tuvieron_ventas_o_tienen_stock():
    en_archivo = _ref("A")
    con_ventas, con_stock, con_ambos, limpia = _ref("V"), _ref("S"), _ref("VS"), _ref("L")
    plan, _ = await _plan(
        [en_archivo, con_ventas, con_stock, con_ambos, limpia], [_fila("A")],
        ventas=[con_ventas.id, con_ambos.id], fecha_corte=datetime.date(2026, 9, 21),
        con_stock=[con_stock.id, con_ambos.id])

    ausentes = reemplazo_referencias.construir_resumen(plan).ausentes

    assert ausentes.total == 4 and ausentes.con_ventas_6m == 2 and ausentes.con_inventario == 2
    por_codigo = {m["codigo"]: m for m in ausentes.items}
    assert por_codigo["V"]["con_ventas_6m"] is True and por_codigo["V"]["con_inventario"] is False
    assert por_codigo["S"]["con_ventas_6m"] is False and por_codigo["S"]["con_inventario"] is True
    assert por_codigo["L"]["con_ventas_6m"] is False and por_codigo["L"]["con_inventario"] is False
    assert ausentes.items[-1]["codigo"] == "L"  # las resaltadas van primero
    assert set(por_codigo["V"]) >= {"codigo", "nombre", "proveedor", "con_ventas_6m", "con_inventario"}
    assert por_codigo["V"]["proveedor"] == "HMCL"


async def test_la_lista_de_ausentes_es_completa_mas_alla_de_50():
    referencias = [_ref("A")] + [_ref(f"X-{i:03d}") for i in range(80)]

    plan, _ = await _plan(referencias, [_fila("A")])
    ausentes = reemplazo_referencias.construir_resumen(plan).ausentes

    assert ausentes.total == 80 and len(ausentes.items) == 80


async def test_demasiadas_ausentes_para_listar_es_un_error_claro(monkeypatch):
    monkeypatch.setattr(reemplazo_referencias, "AUSENTES_MAX", 5)
    referencias = [_ref("A")] + [_ref(f"X-{i}") for i in range(6)]

    plan, _ = await _plan(referencias, [_fila("A")])

    with pytest.raises(reemplazo_referencias.DemasiadasAusentes) as exc:
        reemplazo_referencias.construir_resumen(plan)
    assert "6" in str(exc.value) and "5" in str(exc.value)


@pytest.mark.parametrize("elegidas,requiere", [(1, False), (2, False), (3, True)])
async def test_doble_confirmacion_solo_si_lo_elegido_pasa_del_10_por_ciento(elegidas, requiere):
    # 20 activas: 10% = 2 -> exactamente 10% NO exige; mas de 10% si. Las ausentes
    # son 10, pero solo cuenta lo que se elige.
    referencias = [_ref(f"R-{i}") for i in range(20)]
    filas = [_fila(r.codigo) for r in referencias[10:]]

    plan, _ = await _plan(referencias, filas)
    resumen = reemplazo_referencias.construir_resumen(plan, [f"R-{i}" for i in range(elegidas)])

    assert resumen.ausentes.total == 10 and resumen.activas_actuales == 20
    assert resumen.seleccionadas == elegidas
    assert resumen.pct_inactivar == pytest.approx(elegidas / 20)
    assert resumen.pct_inactivar_si_todas == pytest.approx(10 / 20)
    assert resumen.requiere_doble_confirmacion is requiere


async def test_sin_elegir_nada_el_dry_run_no_pide_doble_confirmacion_aunque_falten_muchas():
    referencias = [_ref(f"R-{i}") for i in range(20)]

    plan, _ = await _plan(referencias, [_fila("R-0")])
    resumen = reemplazo_referencias.construir_resumen(plan)

    assert resumen.ausentes.total == 19 and resumen.pct_inactivar == 0
    assert resumen.requiere_doble_confirmacion is False


async def test_sin_referencias_activas_el_porcentaje_es_cero():
    plan, _ = await _plan([], [_fila("NUEVA")])
    resumen = reemplazo_referencias.construir_resumen(plan)

    assert resumen.pct_inactivar == 0 and resumen.requiere_doble_confirmacion is False


# --- Confirmaciones al aplicar -----------------------------------------------------


async def test_aplicar_sin_confirmar_el_reemplazo_es_409_y_no_escribe_nada():
    existente = _ref("A", nombre="Original")
    db = _db([existente])

    with pytest.raises(HTTPException) as exc:
        await carga.procesar_carga(db, "referencia", [_fila("A", nombre="Nueva")])

    assert exc.value.status_code == 409 and "reemplazo" in exc.value.detail.lower()
    assert existente.nombre == "Original" and db.committed is False


async def test_aplicar_que_desactiva_mas_del_10_por_ciento_sin_doble_confirmacion_es_409():
    referencias = [_ref(f"R-{i}") for i in range(10)]
    db = _db(referencias)

    with pytest.raises(HTTPException) as exc:
        await carga.procesar_carga(
            db, "referencia", [_fila("R-0")], confirmar_reemplazo=True,
            codigos_inactivar=[f"R-{i}" for i in range(1, 10)])

    assert exc.value.status_code == 409 and "%" in exc.value.detail
    assert all(r.activa for r in referencias) and db.committed is False


async def test_con_la_doble_confirmacion_se_aplica():
    referencias = [_ref(f"R-{i}") for i in range(10)]

    resultado, db = await _aplicar(referencias, [_fila("R-0")], confirmar_masiva=True,
                                   codigos_inactivar=[f"R-{i}" for i in range(1, 10)])

    assert resultado.ok is True and db.committed is True
    assert [r.activa for r in referencias] == [True] + [False] * 9


async def test_aplicar_sin_elegir_ausentes_no_exige_doble_confirmacion_aunque_falten_muchas():
    referencias = [_ref(f"R-{i}") for i in range(10)]

    resultado, db = await _aplicar(referencias, [_fila("R-0")])

    assert resultado.ok is True and db.committed is True
    assert all(r.activa for r in referencias)


async def test_la_confirmacion_masiva_no_hace_falta_bajo_el_umbral():
    resultado, db = await _aplicar([_ref("A"), _ref("B")], [_fila("A"), _fila("B")])

    assert resultado.ok is True and db.committed is True


async def test_aplicar_deja_un_asiento_de_auditoria_con_el_resumen():
    existente, ausente = _ref("A"), _ref("B")

    otra = _ref("C")
    _, db = await _aplicar([existente, ausente, otra], [_fila("A")], codigos_inactivar=["B"],
                           confirmar_masiva=True)

    asientos = [a for a in db.added_of_type(AuditoriaMaestro) if a.campo == "reemplazo_masivo"]
    assert len(asientos) == 1
    assert "ausentes_ofrecidas=2" in asientos[0].valor_nuevo
    assert "inactivar_elegidas=1" in asientos[0].valor_nuevo and asientos[0].entidad == "referencia_reemplazo"


async def test_aplicar_devuelve_el_resumen_de_lo_aplicado():
    resultado, _ = await _aplicar([_ref("A"), _ref("B")], [_fila("A"), _fila("NUEVA")],
                                  codigos_inactivar=["B"], confirmar_masiva=True)

    assert resultado.resumen_reemplazo.crear.total == 1
    assert resultado.resumen_reemplazo.ausentes.total == 1
    assert resultado.resumen_reemplazo.seleccionadas == 1
    assert resultado.insertados == 1


# --- Las demas entidades no cambian ---------------------------------------------------


async def test_otras_entidades_siguen_con_celda_en_blanco_igual_a_no_provisto():
    existente = Sucursal(id=uuid.uuid4(), nombre="CALI NORTE", sic="S1", activa=True)
    db = FakeAsyncSession(execute_queue=[[existente]])

    resultado = await carga.procesar_carga(db, "sucursal", [{"nombre": "CALI NORTE", "sic": ""}])

    assert resultado.ok is True and existente.sic == "S1"
