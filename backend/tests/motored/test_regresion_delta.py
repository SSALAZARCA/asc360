"""
Motored Pedidos F3 "Motor" (S8b-1, ADR-10, Level C) — medición por switch.

Cada switch de desviación se enciende SOLO y luego todos juntos; cada escenario
se compara con la línea base (todo apagado) y produce un delta: líneas
cambiadas, unidades, valor, movimientos de clase y líneas transferidas. Sin
pasa/falla. Estos tests usan el motor puro con insumos sintéticos y la fila
patrón §10.1 (con el mes en curso: §10.1-PONDERADO, pedido 61).
"""
from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

from app.motored.herramientas.regresion.delta import (
    ConjuntoLineas,
    Escenario,
    Excluida,
    InsumosMemoria,
    LineaComparable,
    calcular_delta,
    conjunto_desde_resultado,
    escenarios_estandar,
    medir_en_memoria,
)
from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.sustitucion import resolver_cadenas
from app.motored.services.motor.tipos import (
    MesEnCurso,
    NodoMaestro,
    ParametrosMotor,
)
from tests.motored.fixtures.motor.constructores import (
    atributos,
    entrada,
    fila_patron,
)

CORTE = date(2026, 9, 21)
ID_A = UUID(int=11)
ID_B = UUID(int=12)
BASE = "Línea base (todo apagado)"


def _linea(codigo, clase, pedido, valor, n="1"):
    return LineaComparable(
        codigo, clase, Decimal(n), Decimal(pedido), Decimal(valor)
    )


def _conjunto(*lineas, excluidas=()):
    por_codigo = {linea.codigo: linea for linea in lineas}
    return ConjuntoLineas(por_codigo, tuple(excluidas))


def _insumos(entradas, **cambios):
    base = InsumosMemoria(
        entradas=tuple(entradas),
        atributos=atributos(nombre="SUCURSAL MEDIDA", fecha_corte=CORTE),
        params=ParametrosMotor(),
    )
    return replace(base, **cambios)


def _por_nombre(resultados):
    return {r.escenario.nombre: r for r in resultados}


class TestEscenariosEstandar:
    def test_lista_un_escenario_por_switch_y_el_combinado(self):
        nombres = [e.nombre for e in escenarios_estandar()]
        assert nombres == [
            "perdida x1", "consolidar_sustituidas", "dias_entre_pedidos=7",
            "dias_entre_pedidos=15", "mes_en_curso=PONDERADO",
            "excluir_transito_vencido", "combinado",
        ]

    def test_cada_switch_va_solo_en_su_escenario(self):
        por_nombre = {e.nombre: e for e in escenarios_estandar()}
        assert por_nombre["perdida x1"].overrides == {
            "incluir_demanda_perdida_en_ponderada": True,
            "factor_demanda_perdida": "1",
        }
        assert por_nombre["consolidar_sustituidas"].overrides == {
            "consolidar_sustituidas": True
        }
        assert por_nombre["dias_entre_pedidos=15"].overrides == {
            "dias_entre_pedidos": 15
        }

    def test_acepta_otros_factores_y_otros_dias(self):
        nombres = [
            e.nombre for e in escenarios_estandar(
                factores=("1", "2.5"), dias=(10,)
            )
        ]
        assert "perdida x2.5" in nombres
        assert "dias_entre_pedidos=10" in nombres
        assert "dias_entre_pedidos=7" not in nombres

    def test_el_combinado_enciende_todo_a_la_vez(self):
        combinado = escenarios_estandar()[-1]
        assert combinado.overrides == {
            "incluir_demanda_perdida_en_ponderada": True,
            "factor_demanda_perdida": "1",
            "consolidar_sustituidas": True,
            "dias_entre_pedidos": 7,
            "modo_mes_en_curso": "PONDERADO",
            "excluir_transito_vencido": True,
        }


class TestConjuntoDesdeResultado:
    def test_cuantiza_las_lineas_del_motor(self):
        resultado = calcular_sucursal(
            [fila_patron()], atributos(fecha_corte=CORTE), ParametrosMotor()
        )
        conjunto = conjunto_desde_resultado(resultado)
        linea = conjunto.lineas["94109-12000S"]
        assert linea == _linea(
            "94109-12000S", "CF", "50", "23037.50", "85.428571"
        )
        assert conjunto.excluidas == ()

    def test_trae_las_excluidas_con_su_sustituta(self):
        viejo = entrada((5, 0, 3, 0, 2, 4), codigo="REF-A",
                        referencia_id=ID_A)
        nuevo = entrada((1,) * 6, codigo="REF-B", referencia_id=ID_B)
        resultado = calcular_sucursal(
            [viejo, nuevo], atributos(fecha_corte=CORTE),
            ParametrosMotor(consolidar_sustituidas=True),
            resolver_cadenas({ID_A: NodoMaestro(ID_A, False, ID_B)}),
        )
        conjunto = conjunto_desde_resultado(resultado)
        assert conjunto.excluidas == (
            Excluida("REF-A", "SUSTITUIDA", "REF-B"),
        )
        assert set(conjunto.lineas) == {"REF-B"}


class TestCalcularDelta:
    def _delta(self):
        base = _conjunto(
            _linea("A", "AF", "10", "100"),
            _linea("B", "BM", "5", "50"),
            _linea("C", "CS", "0", "0"),
        )
        escenario = _conjunto(
            _linea("A", "AF", "14", "140"),
            _linea("B", "BF", "5", "50"),
            _linea("D", "CM", "3", "30"),
            excluidas=[Excluida("C", "SUSTITUIDA", "D")],
        )
        return calcular_delta(base, escenario)

    def test_totales_de_unidades_y_valor(self):
        delta = self._delta()
        assert (delta.unidades_base, delta.unidades_escenario) == (15, 22)
        assert (delta.valor_base, delta.valor_escenario) == (150, 220)
        assert (delta.lineas_base, delta.lineas_escenario) == (3, 3)

    def test_cuenta_lineas_con_pedido_distinto_y_movimientos_de_clase(self):
        delta = self._delta()
        assert delta.lineas_cambiadas == 2
        assert delta.movimientos_clase == 1

    def test_el_detalle_distingue_cambio_nueva_y_quitada(self):
        delta = self._delta()
        tipos = {c.codigo: c.tipo for c in delta.cambios}
        assert tipos == {
            "A": "CAMBIO", "B": "CAMBIO", "C": "QUITADA", "D": "NUEVA",
        }
        a = next(c for c in delta.cambios if c.codigo == "A")
        assert (a.pedido_base, a.pedido_escenario) == (10, 14)
        assert (a.valor_base, a.valor_escenario) == (100, 140)

    def test_las_transferidas_vienen_del_escenario(self):
        assert self._delta().transferidas == (
            Excluida("C", "SUSTITUIDA", "D"),
        )

    def test_una_inactiva_sin_reemplazo_no_cuenta_como_transferida(self):
        base = _conjunto(_linea("A", "AF", "10", "100"))
        escenario = _conjunto(
            _linea("B", "AF", "10", "100"),
            excluidas=[
                Excluida("A", "SUSTITUIDA", "B"),
                Excluida("C", "INACTIVA_SIN_REEMPLAZO", None),
            ],
        )
        delta = calcular_delta(base, escenario)
        assert delta.transferidas == (Excluida("A", "SUSTITUIDA", "B"),)

    def test_dos_conjuntos_iguales_no_cambian_nada(self):
        conjunto = _conjunto(_linea("A", "AF", "10", "100"))
        delta = calcular_delta(conjunto, conjunto)
        assert delta.cambios == ()
        assert delta.lineas_cambiadas == delta.movimientos_clase == 0


class TestMedirEnMemoria:
    def test_dias_entre_pedidos_7_baja_el_pedido_de_la_fila_patron(self):
        resultados = medir_en_memoria(
            _insumos([fila_patron()]), escenarios_estandar()
        )
        por_nombre = _por_nombre(resultados)
        delta = por_nombre["dias_entre_pedidos=7"].delta
        assert delta.unidades_base == 50 and delta.unidades_escenario == 0
        assert delta.valor_base == Decimal("23037.50")
        assert delta.valor_escenario == 0
        assert delta.lineas_cambiadas == 1

    def test_la_primera_fila_es_la_linea_base_sin_delta(self):
        resultados = medir_en_memoria(
            _insumos([fila_patron()]), escenarios_estandar()
        )
        assert resultados[0].escenario.nombre == BASE
        assert resultados[0].delta is None
        assert resultados[0].conjunto.lineas["94109-12000S"].pedido == 50

    def test_la_demanda_perdida_sube_n_y_el_pedido(self):
        sube = entrada((10,) * 6, (0, 0, 0, 0, 0, 6), codigo="P-1")
        resultados = medir_en_memoria(
            _insumos([sube]), escenarios_estandar()
        )
        delta = _por_nombre(resultados)["perdida x1"].delta
        assert delta.unidades_base == 18
        assert delta.unidades_escenario == 21
        assert delta.lineas_cambiadas == 1

    def test_el_factor_se_aplica_por_escenario(self):
        sube = entrada((10,) * 6, (0, 0, 0, 0, 0, 6), codigo="P-1")
        resultados = medir_en_memoria(
            _insumos([sube]), escenarios_estandar(factores=("1", "2"))
        )
        por_nombre = _por_nombre(resultados)
        assert (
            por_nombre["perdida x2"].delta.unidades_escenario
            > por_nombre["perdida x1"].delta.unidades_escenario
        )

    def test_consolidar_lista_la_vieja_como_transferida(self):
        viejo = entrada((5, 0, 3, 0, 2, 4), codigo="REF-A",
                        referencia_id=ID_A, inventario=2)
        nuevo = entrada((1,) * 6, codigo="REF-B", referencia_id=ID_B)
        insumos = _insumos(
            [viejo, nuevo],
            resoluciones=resolver_cadenas(
                {ID_A: NodoMaestro(ID_A, False, ID_B)}
            ),
        )
        delta = _por_nombre(
            medir_en_memoria(insumos, escenarios_estandar())
        )["consolidar_sustituidas"].delta
        assert delta.lineas_base == 2 and delta.lineas_escenario == 1
        assert delta.transferidas == (
            Excluida("REF-A", "SUSTITUIDA", "REF-B"),
        )

    def test_ponderado_con_el_mes_en_curso_da_pedido_61(self):
        patron = replace(fila_patron(), venta_m0=Decimal(63))
        insumos = _insumos(
            [patron], mes_en_curso=MesEnCurso("PONDERADO", 14, 30, Fraction(3))
        )
        resultados = medir_en_memoria(insumos, escenarios_estandar())
        delta = _por_nombre(resultados)["mes_en_curso=PONDERADO"].delta
        assert delta.unidades_escenario == 61
        assert delta.unidades_base == 50
        assert delta.valor_escenario - delta.valor_base == Decimal("5068.25")

    def test_lo_que_los_insumos_no_permiten_medir_se_explica(self):
        resultados = medir_en_memoria(
            _insumos([fila_patron()]), escenarios_estandar()
        )
        por_nombre = _por_nombre(resultados)
        sin_medir = {
            nombre: r.motivo_no_medido for nombre, r in por_nombre.items()
            if r.delta is None and nombre != BASE
        }
        assert set(sin_medir) == {
            "perdida x1", "consolidar_sustituidas",
            "mes_en_curso=PONDERADO", "excluir_transito_vencido",
            "combinado",
        }
        assert "demanda perdida" in sin_medir["perdida x1"]
        assert "sustitución" in sin_medir["consolidar_sustituidas"]
        assert "mes en curso" in sin_medir["mes_en_curso=PONDERADO"]
        assert "base de datos" in sin_medir["excluir_transito_vencido"]
        assert "dos" in sin_medir["combinado"]

    def test_el_combinado_reune_los_switches_medibles(self):
        sube = entrada((10,) * 6, (0, 0, 0, 0, 0, 6), codigo="P-1")
        resultados = medir_en_memoria(
            _insumos([sube]), escenarios_estandar()
        )
        combinado = _por_nombre(resultados)["combinado"]
        assert combinado.delta is not None
        assert "dias_entre_pedidos" in combinado.nota
        assert "Omitidos" in combinado.nota
        assert "consolidar_sustituidas" in combinado.nota

    def test_los_parametros_de_base_no_se_tocan(self):
        insumos = _insumos([fila_patron()])
        medir_en_memoria(insumos, escenarios_estandar())
        assert insumos.params == ParametrosMotor()
        assert insumos.atributos.dias_entre_pedidos == Decimal(30)


def test_un_override_desconocido_no_se_puede_medir_en_memoria():
    raro = Escenario("raro", "clave inventada", {"clave_inventada": 1})
    (base, medido) = medir_en_memoria(_insumos([fila_patron()]), [raro])
    assert base.escenario.nombre == BASE
    assert medido.delta is None
    assert "clave_inventada" in medido.motivo_no_medido


def test_sin_escenarios_solo_queda_la_linea_base():
    (base,) = medir_en_memoria(_insumos([fila_patron()]), [])
    assert base.escenario.nombre == BASE
    assert base.delta is None and base.motivo_no_medido is None
    assert base.conjunto is not None
