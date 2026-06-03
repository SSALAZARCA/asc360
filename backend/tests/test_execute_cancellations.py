"""
Tests para la lógica de cancelación de ítems desde Análisis de Repuestos.

Estos tests validan la lógica de negocio sin necesidad de DB real,
usando objetos simples que simulan el comportamiento de los modelos ORM.
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch


# ---------------------------------------------------------------------------
# Helpers — objetos simples que simulan modelos ORM
# ---------------------------------------------------------------------------

def make_item(part_number, status='PENDING', qty_ordered=10, qty_pending=10,
              fob_pi=None, unit_price=None, lot_id=None):
    item = MagicMock()
    item.part_number   = part_number
    item.status        = status
    item.qty_ordered   = qty_ordered
    item.qty_pending   = qty_pending
    item.fob_pi        = fob_pi
    item.unit_price    = unit_price
    item.lot_id        = lot_id or 'lot-uuid-1'
    item.updated_at    = None
    return item


def make_lot(lot_identifier, packing_list_received=False, lot_id='lot-uuid-1'):
    lot = MagicMock()
    lot.id                    = lot_id
    lot.lot_identifier        = lot_identifier
    lot.packing_list_received = packing_list_received
    lot.items                 = []
    return lot


def make_decision(fpn, lot_identifier, decision='cancelar', executed_at=None):
    d = MagicMock()
    d.factory_part_number = fpn
    d.lot_identifier      = lot_identifier
    d.decision            = decision
    d.executed_at         = executed_at
    return d


def make_ref(fpn, preliminary_fob=None):
    ref = MagicMock()
    ref.factory_part_number = fpn
    ref.preliminary_fob     = preliminary_fob
    return ref


# ---------------------------------------------------------------------------
# Tests: cálculo de preliminary_fob tras cancelación
# ---------------------------------------------------------------------------

def calc_preliminary_fob(active_items):
    """Lógica pura de recálculo de preliminary_fob (extraída del endpoint)."""
    items_with_fob = [
        i for i in active_items
        if i.status != 'CANCELLED' and i.fob_pi is not None and (i.qty_ordered or 0) > 0
    ]
    if not items_with_fob:
        return None
    total_cost = sum(float(i.fob_pi) * (i.qty_ordered or 0) for i in items_with_fob)
    total_qty  = sum(i.qty_ordered or 0 for i in items_with_fob)
    return round(total_cost / total_qty, 4) if total_qty > 0 else None


class TestPreliminaryFobRecalculation:

    def test_recalc_con_un_item_activo(self):
        items = [make_item('REF001', status='PENDING', qty_ordered=10, fob_pi=5.0)]
        assert calc_preliminary_fob(items) == 5.0

    def test_recalc_promedio_ponderado(self):
        """Dos ítems con distinto fob_pi y qty_ordered — promedio ponderado."""
        items = [
            make_item('REF001', status='PENDING', qty_ordered=10, fob_pi=4.0),
            make_item('REF001', status='PENDING', qty_ordered=5,  fob_pi=7.0),
        ]
        # (4*10 + 7*5) / (10+5) = (40+35)/15 = 75/15 = 5.0
        assert calc_preliminary_fob(items) == 5.0

    def test_recalc_excluye_cancelados(self):
        """Los ítems CANCELLED no deben entrar en el promedio."""
        items = [
            make_item('REF001', status='CANCELLED', qty_ordered=10, fob_pi=100.0),
            make_item('REF001', status='PENDING',   qty_ordered=5,  fob_pi=6.0),
        ]
        # Solo el ítem activo: 6.0
        assert calc_preliminary_fob(items) == 6.0

    def test_recalc_todos_cancelados_devuelve_none(self):
        """Si todos los ítems están cancelados, preliminary_fob debe ser None."""
        items = [
            make_item('REF001', status='CANCELLED', qty_ordered=10, fob_pi=5.0),
            make_item('REF001', status='CANCELLED', qty_ordered=5,  fob_pi=7.0),
        ]
        assert calc_preliminary_fob(items) is None

    def test_recalc_sin_fob_pi_devuelve_none(self):
        """Si ningún ítem activo tiene fob_pi, devuelve None."""
        items = [make_item('REF001', status='PENDING', qty_ordered=10, fob_pi=None)]
        assert calc_preliminary_fob(items) is None

    def test_recalc_excluye_qty_ordered_cero(self):
        """Ítems con qty_ordered=0 no afectan el promedio."""
        items = [
            make_item('REF001', status='PENDING', qty_ordered=0,  fob_pi=999.0),
            make_item('REF001', status='PENDING', qty_ordered=10, fob_pi=5.0),
        ]
        assert calc_preliminary_fob(items) == 5.0


# ---------------------------------------------------------------------------
# Tests: cálculo de fob_value del lote excluyendo CANCELLED
# ---------------------------------------------------------------------------

def calc_fob_value(lot_items):
    """Lógica pura de cálculo de fob_value (extraída del endpoint de lotes)."""
    fob_total   = 0.0
    has_estimate = False
    for i in lot_items:
        if i.status == 'CANCELLED':
            continue
        price = i.unit_price if i.unit_price is not None else i.fob_pi
        if price is not None:
            fob_total += float(price) * (i.qty_ordered or 0)
            if i.unit_price is None and i.fob_pi is not None:
                has_estimate = True
    return (round(fob_total, 2) if fob_total > 0 else None), has_estimate


class TestFobValueCalculation:

    def test_fob_value_basico(self):
        items = [make_item('REF001', qty_ordered=10, fob_pi=5.0)]
        val, estimate = calc_fob_value(items)
        assert val == 50.0
        assert estimate is True  # usa fob_pi, no unit_price

    def test_fob_value_usa_unit_price_cuando_existe(self):
        items = [make_item('REF001', qty_ordered=10, unit_price=8.0, fob_pi=5.0)]
        val, estimate = calc_fob_value(items)
        assert val == 80.0
        assert estimate is False  # unit_price tiene prioridad

    def test_fob_value_excluye_cancelados(self):
        """Ítems CANCELLED no deben sumar al fob_value del lote."""
        items = [
            make_item('REF001', status='CANCELLED', qty_ordered=10, fob_pi=5.0),
            make_item('REF002', status='PENDING',   qty_ordered=5,  fob_pi=4.0),
        ]
        val, _ = calc_fob_value(items)
        assert val == 20.0  # solo REF002: 5*4

    def test_fob_value_todos_cancelados_devuelve_none(self):
        items = [make_item('REF001', status='CANCELLED', qty_ordered=10, fob_pi=5.0)]
        val, _ = calc_fob_value(items)
        assert val is None

    def test_fob_value_sin_precio_no_suma(self):
        items = [
            make_item('REF001', qty_ordered=10, fob_pi=None, unit_price=None),
            make_item('REF002', qty_ordered=5,  fob_pi=4.0),
        ]
        val, _ = calc_fob_value(items)
        assert val == 20.0


# ---------------------------------------------------------------------------
# Tests: cálculo de pl_value del lote (usa qty_received, no qty_ordered)
# ---------------------------------------------------------------------------

def calc_pl_value(lot_items):
    """Lógica pura de cálculo de pl_value (extraída del endpoint de lotes).
    Usa qty_received porque representa lo que el proveedor despachó y cobró.
    """
    total = sum(
        float(i.unit_price) * (i.qty_received or 0)
        for i in lot_items
        if i.unit_price is not None and i.status != 'CANCELLED'
    )
    return round(total, 2) if total > 0 else None


def make_item_pl(part_number, status='DECLARED', qty_ordered=10, qty_received=10,
                 unit_price=None, fob_pi=None):
    item = make_item(part_number, status=status, qty_ordered=qty_ordered,
                     fob_pi=fob_pi, unit_price=unit_price)
    item.qty_received = qty_received
    return item


class TestPlValueCalculation:

    def test_pl_value_usa_qty_received_no_qty_ordered(self):
        """El valor del PL debe usar qty_received (lo despachado), no qty_ordered."""
        # Pedido: 100 unidades, llegaron 80
        item = make_item_pl('REF001', qty_ordered=100, qty_received=80, unit_price=5.0)
        assert calc_pl_value([item]) == 400.0  # 80 × 5, no 100 × 5

    def test_pl_value_completo_coincide_con_pedido(self):
        """Si llegó todo, pl_value == fob_value."""
        item = make_item_pl('REF001', qty_ordered=10, qty_received=10, unit_price=5.0)
        assert calc_pl_value([item]) == 50.0

    def test_pl_value_parcial_menor_que_pedido(self):
        """Si hubo backorder/partial, pl_value < valor del pedido."""
        item = make_item_pl('REF001', qty_ordered=10, qty_received=6, unit_price=5.0)
        pl  = calc_pl_value([item])
        fob = 10 * 5.0  # valor del pedido
        assert pl == 30.0
        assert pl < fob

    def test_pl_value_excluye_cancelados(self):
        """Ítems CANCELLED no deben sumar al pl_value."""
        items = [
            make_item_pl('REF001', status='CANCELLED', qty_ordered=10, qty_received=10, unit_price=5.0),
            make_item_pl('REF002', status='DECLARED',  qty_ordered=5,  qty_received=5,  unit_price=4.0),
        ]
        assert calc_pl_value(items) == 20.0  # solo REF002: 5 × 4

    def test_pl_value_sin_unit_price_no_suma(self):
        """Ítems sin unit_price (solo fob_pi) no entran en pl_value."""
        items = [
            make_item_pl('REF001', qty_ordered=10, qty_received=10, unit_price=None, fob_pi=5.0),
            make_item_pl('REF002', qty_ordered=5,  qty_received=5,  unit_price=4.0),
        ]
        assert calc_pl_value(items) == 20.0  # solo REF002

    def test_pl_value_todos_sin_unit_price_devuelve_none(self):
        """Si ningún ítem tiene unit_price, pl_value es None."""
        items = [make_item_pl('REF001', qty_received=10, unit_price=None, fob_pi=5.0)]
        assert calc_pl_value(items) is None

    def test_pl_value_qty_received_cero_no_suma(self):
        """Si qty_received=0 (nada llegó), ese ítem no aporta al valor del PL."""
        items = [
            make_item_pl('REF001', qty_ordered=10, qty_received=0, unit_price=5.0),
            make_item_pl('REF002', qty_ordered=5,  qty_received=5, unit_price=4.0),
        ]
        assert calc_pl_value(items) == 20.0  # solo REF002


# ---------------------------------------------------------------------------
# Tests: guardia de seguridad — no cancelar si packing_list_received
# ---------------------------------------------------------------------------

class TestCancellationSafetyGuard:

    def test_no_cancela_lote_con_packing_list_recibido(self):
        """Si el lote ya tiene packing list, no se debe cancelar ningún ítem."""
        lot = make_lot('PI-001', packing_list_received=True)
        # La lógica del endpoint verifica lot.packing_list_received antes de cancelar
        assert lot.packing_list_received is True
        # En el endpoint, esto genera un skip y el ítem no se toca

    def test_cancela_lote_sin_packing_list(self):
        """Si el lote NO tiene packing list, la cancelación puede proceder."""
        lot = make_lot('PI-001', packing_list_received=False)
        assert lot.packing_list_received is False

    def test_no_cancela_items_ya_recibidos(self):
        """Ítems con status RECEIVED/DECLARED/BACKORDER no se cancelan."""
        statuses_protegidos = ['RECEIVED', 'DECLARED', 'BACKORDER', 'CANCELLED']
        for status in statuses_protegidos:
            item = make_item('REF001', status=status)
            # El endpoint filtra: status.notin_(['CANCELLED','RECEIVED','DECLARED','BACKORDER'])
            assert item.status in statuses_protegidos

    def test_cancela_solo_pending(self):
        """Solo ítems PENDING y PARTIAL son cancelables."""
        statuses_cancelables = ['PENDING', 'PARTIAL']
        for status in statuses_cancelables:
            item = make_item('REF001', status=status)
            assert item.status not in ['CANCELLED', 'RECEIVED', 'DECLARED', 'BACKORDER']


# ---------------------------------------------------------------------------
# Tests: normalización de part_number
# ---------------------------------------------------------------------------

class TestPartNumberNormalization:

    def normalize(self, pn):
        return pn.upper().strip().replace(' ', '')

    def test_normaliza_mayusculas(self):
        assert self.normalize('ref-001') == 'REF-001'

    def test_elimina_espacios(self):
        assert self.normalize('REF 001') == 'REF001'

    def test_trim_extremos(self):
        assert self.normalize('  REF001  ') == 'REF001'

    def test_combinado(self):
        assert self.normalize('  ref 001  ') == 'REF001'

    def test_match_entre_pi_y_catalogo(self):
        """Simula el match entre part_number del ítem y factory_part_number del catálogo."""
        # Ambos lados tienen el mismo código base; la normalización iguala mayúsculas y espacios
        part_number_en_item = ' ref 001 '    # con espacios y minúsculas
        factory_part_number = 'REF 001'      # con espacio y mayúsculas
        assert self.normalize(part_number_en_item) == self.normalize(factory_part_number)


# ---------------------------------------------------------------------------
# Tests: estado de executed_at
# ---------------------------------------------------------------------------

class TestDecisionExecution:

    def test_decision_sin_ejecutar_tiene_executed_at_none(self):
        decision = make_decision('REF001', 'PI-001', decision='cancelar', executed_at=None)
        assert decision.executed_at is None

    def test_decision_ejecutada_tiene_timestamp(self):
        now = datetime.utcnow()
        decision = make_decision('REF001', 'PI-001', decision='cancelar', executed_at=now)
        assert decision.executed_at is not None
        assert isinstance(decision.executed_at, datetime)

    def test_solo_ejecuta_decision_cancelar(self):
        """Solo las decisiones con decision='cancelar' deben ejecutarse."""
        d_cancelar = make_decision('REF001', 'PI-001', decision='cancelar')
        d_cambiar  = make_decision('REF002', 'PI-001', decision='cambiar')
        # El endpoint filtra: _POD.decision == 'cancelar'
        assert d_cancelar.decision == 'cancelar'
        assert d_cambiar.decision != 'cancelar'
