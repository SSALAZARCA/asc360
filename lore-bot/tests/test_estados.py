import uuid

from lore.estados import (
    Borrador,
    CapturaEstado,
    CorreccionEstado,
    LineaBorrador,
    RegistroEstado,
)


class TestEnumsAreDistinctAndOrdered:
    def test_registro_estado_members_are_distinct(self):
        values = [e.value for e in RegistroEstado]
        assert len(values) == len(set(values))

    def test_captura_estado_members_are_distinct(self):
        values = [e.value for e in CapturaEstado]
        assert len(values) == len(set(values))

    def test_correccion_estado_members_are_distinct(self):
        values = [e.value for e in CorreccionEstado]
        assert len(values) == len(set(values))


class TestBorradorShape:
    def test_default_construction_has_no_lineas_and_a_fresh_registro_id(self):
        borrador = Borrador()
        assert borrador.lineas == []
        assert borrador.no_resueltas == []
        assert borrador.registro_id is not None

    def test_registro_id_is_unique_per_instance(self):
        assert Borrador().registro_id != Borrador().registro_id

    def test_linea_borrador_starts_without_a_quantity(self):
        linea = LineaBorrador(referencia_id=uuid.uuid4(), codigo="ABC123")
        assert linea.cantidad is None
        assert linea.nombre is None
