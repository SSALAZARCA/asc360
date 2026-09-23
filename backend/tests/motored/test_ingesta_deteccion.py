"""
Motored Pedidos — Fase 3 "Cargas: Tipo Declarado" (sdd/motored-cargas-tipo-
declarado, Phase 2, task 2.1; design D1 "`_verificar_tipo_o_400` shape").

`services/ingesta/deteccion.py` pasó de DETECTAR `tipo` (elegir uno de 6 a
partir de la firma de encabezado) a VERIFICAR un `tipo` DECLARADO por el
caller. Este módulo no tenía tests unitarios dedicados antes de este cambio
-- `detectar_tipo` solo se probaba indirectamente vía `test_cargas_api.py`.
Estos son los primeros unit tests directos sobre la firma de encabezado,
table-driven sobre los 6 tipos de movimiento (mismas claves que
`orquestador.TIPOS_MOVIMIENTO`), cubriendo los 3 casos que la spec exige
distinguir:
  1. el archivo COINCIDE con el tipo declarado -> `verificar_tipo` no levanta
  2. el archivo NO SE PARECE A NADA conocido -> `sin_coincidencia=True`
  3. el archivo es de OTRO tipo (mismatch parcial) -> `sin_coincidencia=False`
     con `columnas_faltantes` nombrando lo que falta
"""
import pytest

from app.motored.services.ingesta import deteccion

# Mismas tuplas que cada transform declara en su propio `COLUMNAS_ESPERADAS`
# (ver `orquestador._COLUMNAS_POR_TIPO`) -- repetidas acá literalmente, en
# vez de importadas, para que este test no dependa de un import transitivo
# de los 6 módulos de transform con el único propósito de armar una fila de
# encabezado de prueba.
COLUMNAS_POR_TIPO = {
    "VENTAS": (
        "Estado", "Módulo", "Fecha", "Cantidad inv.", "Tipo inventario",
        "Desc.bodega", "Bodega", "Referencia",
    ),
    "INVENTARIO": ("Referencia", "Bodega", "Desc.bodega", "Existencia"),
    "BACKORDER": (
        "SIC", "Sucursal", "Número del pedido", "Estado del pedido",
        "Referencia Parte", "Cantidad Pendiente",
    ),
    "FACTURAS_PEDIDOS": (
        "SIIC", "Sucursal", "Nota crédito", "Factura", "Fecha", "Parte",
        "Cantidad", "Vlr. Total Neto",
    ),
    "INGRESOS_FACTURAS": (
        "Nrodocumento", "Fecha", "Estado", "Dct.referencia", "Valornetolocal",
    ),
    "DEMANDA_PERDIDA": ("sucursal", "sucursal Drive", "Referencia", "Cantidad Solicitada"),
}

_HEADERS_SIN_SENTIDO = ("Columna A", "Columna B", "Columna C")

# Pares (tipo_declarado, tipo_del_archivo) elegidos a mano para que el ratio
# de coincidencia caiga estrictamente ENTRE 0 y `UMBRAL_DETECCION` (0.6) --
# ni un no-match total, ni una coincidencia que el umbral igual aceptaría.
_PARES_MISMATCH = [
    ("VENTAS", "INVENTARIO"),          # ratio 3/8 = 0.375
    ("INVENTARIO", "DEMANDA_PERDIDA"),  # ratio 1/4 = 0.25
    ("BACKORDER", "FACTURAS_PEDIDOS"),  # ratio 1/6 ≈ 0.167
    ("FACTURAS_PEDIDOS", "INGRESOS_FACTURAS"),  # ratio 1/8 = 0.125
    ("INGRESOS_FACTURAS", "VENTAS"),   # ratio 2/5 = 0.4
    ("DEMANDA_PERDIDA", "BACKORDER"),  # ratio 1/4 = 0.25
]


@pytest.mark.parametrize("tipo", COLUMNAS_POR_TIPO)
def test_verificar_tipo_acepta_archivo_que_coincide_con_el_declarado(tipo):
    encabezado = COLUMNAS_POR_TIPO[tipo]
    filas = [encabezado, tuple(f"valor{i}" for i in range(len(encabezado)))]

    deteccion.verificar_tipo(tipo, filas)  # no debe levantar ninguna excepción


@pytest.mark.parametrize("tipo", COLUMNAS_POR_TIPO)
def test_verificar_tipo_rechaza_sin_ninguna_coincidencia(tipo):
    filas = [_HEADERS_SIN_SENTIDO]

    with pytest.raises(deteccion.TipoNoCoincideError) as exc_info:
        deteccion.verificar_tipo(tipo, filas)

    assert exc_info.value.tipo_declarado == tipo
    assert exc_info.value.sin_coincidencia is True
    assert exc_info.value.columnas_faltantes == []


@pytest.mark.parametrize("tipo_declarado,tipo_del_archivo", _PARES_MISMATCH)
def test_verificar_tipo_rechaza_mismatch_nombrando_columnas_faltantes(
    tipo_declarado, tipo_del_archivo
):
    filas = [COLUMNAS_POR_TIPO[tipo_del_archivo]]

    with pytest.raises(deteccion.TipoNoCoincideError) as exc_info:
        deteccion.verificar_tipo(tipo_declarado, filas)

    assert exc_info.value.tipo_declarado == tipo_declarado
    assert exc_info.value.sin_coincidencia is False
    assert len(exc_info.value.columnas_faltantes) > 0
    assert set(exc_info.value.columnas_faltantes) <= set(COLUMNAS_POR_TIPO[tipo_declarado])


def test_verificar_tipo_acepta_si_alguna_fila_escaneada_coincide_aunque_la_primera_no():
    """Las primeras filas de un archivo real pueden ser metadata/títulos --
    `verificar_tipo` debe seguir escaneando hasta encontrar el encabezado
    real, no rendirse en la primera fila (mismo criterio que el
    `detectar_tipo` original, que escaneaba hasta 20 filas)."""
    encabezado = COLUMNAS_POR_TIPO["INVENTARIO"]
    filas = [_HEADERS_SIN_SENTIDO, encabezado, ("REF1", "BA061", "CALI NORTE", 10)]

    deteccion.verificar_tipo("INVENTARIO", filas)  # no debe levantar


def test_deteccion_ya_no_expone_detectar_tipo():
    """`detectar_tipo` -- la función de INFERENCIA -- fue removida (design
    D1: \"detectar_tipo is REMOVED -- zero callers after cutover\"); el
    módulo pasó de \"adivinar cuál\" a \"verificar uno declarado\"."""
    assert not hasattr(deteccion, "detectar_tipo")


def test_extraer_filas_muestra_sigue_disponible_sin_cambios():
    """`extraer_filas_muestra` es infraestructura compartida (lectura
    síncrona y acotada de un `.xlsx`) -- no depende de si la decisión de
    tipo es detección o verificación, y debe sobrevivir el cutover intacta."""
    assert callable(deteccion.extraer_filas_muestra)
