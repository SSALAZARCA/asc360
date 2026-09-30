# Regresión de Motored Pedidos F3 (niveles A, B y C)

Herramientas para comprobar que el motor reproduce la plantilla de Excel
(`PLANTILLA PEDIDO SEPTIEMBRE.xlsx`, hoja `Pedido`), medir cada switch de
desviación y entregar los resultados al dueño como Excel. El código vive en
`backend/app/motored/herramientas/regresion/`; el punto de entrada es
`backend/scripts/motored_regresion.py`.

**Los datos reales nunca entran al repositorio.** Los libros, las
aceptaciones y todos los informes van por argumento o variable de entorno y se
escriben fuera de cualquier árbol git: la herramienta rechaza una carpeta de
salida cuyo árbol tenga un `.git`.

## Variables de entorno

| Variable | Para qué |
|---|---|
| `MOTORED_REGRESION_EXCEL` | Libro de referencia (`--excel`). |
| `MOTORED_REGRESION_SALIDA` | Carpeta de salida (`--salida`). En el script es una **carpeta**; el `cli.py` de S8a la usa como archivo JSON. |
| `MOTORED_REGRESION_ACEPTACIONES` | JSON `{código: categoría}` con las diferencias aceptadas a mano (`--aceptaciones`). |
| `MOTORED_REGRESION_DB_URL` | Base de pruebas `postgresql+asyncpg://...` (`--db-url`), nivel B, delta con base y exportación de una corrida guardada. |

## Cómo correr cada pieza

Desde `backend/` (Python 3.11 con `.venv`):

```
# Nivel A: A1 (fórmulas) y A2 (comportamiento del producto)
python scripts/motored_regresion.py nivel-a --excel LIBRO.xlsx --salida CARPETA

# Efecto de cada switch con los insumos del libro (nivel C, motor puro)
python scripts/motored_regresion.py delta --excel LIBRO.xlsx --salida CARPETA \
    [--factores 1,2] [--dias 7,15]

# Libro de corrida simple para el dueño (insumos del libro, divisor 21)
python scripts/motored_regresion.py exportar-corrida --excel LIBRO.xlsx --salida CARPETA

# Nivel B: pipeline contra una base de pruebas ya cargada (ver abajo)
python scripts/motored_regresion.py nivel-b --excel LIBRO.xlsx --salida CARPETA \
    --db-url URL --sucursal-id UUID --fecha-corte AAAA-MM-DD [--corrida-id UUID]

# Nivel C con base: una corrida escenario real por switch
python scripts/motored_regresion.py delta --salida CARPETA \
    --db-url URL --sucursal-id UUID --fecha-corte AAAA-MM-DD

# Libro de corrida de una corrida guardada
python scripts/motored_regresion.py exportar-corrida --salida CARPETA \
    --db-url URL --corrida-id UUID
```

| Subcomando | Escribe en la carpeta |
|---|---|
| `nivel-a` | `nivel_a.json`, `comparacion_nivel_a.xlsx` |
| `nivel-b` | `comparacion_nivel_b.xlsx` (con A1, A2, B-entradas, B-salidas) |
| `delta` | `efecto_switches.xlsx` |
| `exportar-corrida` | `corrida_<sucursal o código>.xlsx` |

Códigos de salida: `0` todo pasa, `1` algún nivel tiene diferencias sin
categoría, `2` uso incorrecto o error (ruta dentro del repositorio, libro con
otra estructura, etc.). La consola sólo imprime conteos y una muestra acotada.

## Qué compara cada nivel

- **A1**: el motor con `AjustesPrueba` (divisor /18 de las filas marcadas y el
  orden físico y la clasificación fila por fila del Excel) debe coincidir
  exacto en N..AD, en los factores de cobertura y en el resumen AA1:AE11.
- **A2**: el producto real (divisor 21, empates con la misma clase, decisión
  #17). Cada diferencia lleva una categoría de la taxonomía.
- **B**: entradas (E:J ventas, T precio, U unidad, V inventario, W tránsito,
  X backorder) que la ingesta F2 dejó en la base frente al Excel revisado, y
  **después** las salidas con las reglas del A2. La Z sale del Excel (sólo el
  arnés). Una divergencia de entradas se reporta antes que cualquier salida y
  se acepta por código con T6, T7 o T8 en el archivo de aceptaciones.
- **C**: cada switch encendido solo y todos juntos contra la línea base (todo
  apagado): líneas cambiadas, unidades, valor, movimientos de clase y líneas
  transferidas. No hay pasa/falla.

Taxonomía: T1 divisor /18 · T2 cascada en ABC · T3 empate de N · T4 S estática
del Excel · T5 U = 0 · T6 tránsito al corte · T7 datos cambiados tras la
revisión · T8 meses desplazados · T9 frontera binaria de .5 · T10 etiqueta del
resumen. `SIN_CATEGORIA` hace fallar el nivel salvo que esté aceptada.

## Nivel C: qué se puede medir con qué insumos

Con `--excel` el motor corre sobre lo que trae el libro, así que un switch sin
insumos queda **NO MEDIDO** con su motivo en `Resumen switches`:

| Switch | Con el libro | Con base de datos |
|---|---|---|
| `dias_entre_pedidos` 7 y 15 | se mide | se mide |
| demanda perdida (factor 1 y los que se pidan) | no: el libro trae un total, sin mes | se mide |
| `consolidar_sustituidas` | no: sin maestro de sustitución | se mide |
| `modo_mes_en_curso=PONDERADO` | no: sin ventas de M0 | se mide (si el mes en curso no es usable queda EXCLUIDO y la nota lo dice) |
| `excluir_transito_vencido` | no: actúa en el cargador | se mide |
| combinado | sólo con dos o más switches medibles | se mide |

`delta --excel` exige que el nivel A pase antes de medir nada. Con base, los
overrides viven en la corrida escenario (`ESC-...`); el preset de producción
(`parametro_metodologia`) jamás se escribe.

## Nivel B: preparar la base de pruebas

1. Una base Postgres de pruebas migrada (`alembic -c alembic_motored.ini
   upgrade head`).
2. Cargar por la ingesta real de F2 los archivos que el dueño revisó
   (referencias, sucursales, ventas, inventario, backorder, facturas,
   ingresos, demanda perdida).
3. Correr `nivel-b`: crea la corrida base de la sucursal (todos los switches
   apagados) y compara. Las corridas quedan en la base de pruebas.

No hay datos reales en el repositorio: hasta que el dueño entregue los
archivos revisados el nivel B sólo se prueba con datos sintéticos
(`tests/motored/test_regresion_nivel_b.py` y
`tests/motored/pg_real/test_regresion_nivel_b_pg.py`).

## Cómo leer "Antigüedad de datos" (decisión #16)

Cada informe trae esta hoja. Por tipo de insumo (inventario, backorder,
facturas de pedidos, ingresos de facturas) muestra:

- **Fecha de corte del snapshot usado**: de qué día era el dato que entró a la
  corrida;
- **Antigüedad (días)**: corte menos esa fecha (nunca negativa);
- **Límite aplicado (días)**: el máximo que dejó pasar el preflight (7 por
  defecto; el admin lo sube por tipo sin tocar código);
- **Fuente del límite**: `DEFAULT`, `GLOBAL`, etc.

Un informe hecho con un libro de Excel no tiene cargas: la hoja queda con los
cuatro tipos y la fuente explica que el libro no registra fechas.

## Flujo del dueño

1. Baseline: `nivel-a` (y `nivel-b` cuando haya base cargada) con todo
   apagado; debe pasar sin `SIN_CATEGORIA`.
2. Deltas: `delta` y mirar `Resumen switches` y cada hoja `Delta ...`.
3. Encender los switches de a uno (nueva versión de parámetro) y medir.

## Pruebas opt-in

`pytest.ini` deja fuera de la corrida por defecto los marcadores `lento`,
`pg_real` y `regresion`; se activan con `-m` (el último `-m` gana):

```
.venv/bin/python -m pytest tests/motored -q
MOTORED_TEST_PG_URL=postgresql+asyncpg://... .venv/bin/python -m pytest tests/motored -m pg_real -q
MOTORED_REGRESION_EXCEL=LIBRO.xlsx .venv/bin/python -m pytest tests/motored/regresion -m regresion -q
```

`tests/motored/regresion/test_nivel_b.py` necesita además
`MOTORED_REGRESION_DB_URL`, `MOTORED_REGRESION_SUCURSAL_ID` y
`MOTORED_REGRESION_CORTE` (o `MOTORED_REGRESION_CORRIDA_ID`); sin ellas se
omite.
