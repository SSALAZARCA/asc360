"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, ADR-2) — motor de
cálculo PURO.

Sin I/O: nada de SQLAlchemy, modelos, `database` ni `asyncio` (lo garantiza
`tests/motored/test_motor_pureza.py`). La entrada son dataclasses inmutables de
UNA sucursal; toda la aritmética es exacta (`fractions.Fraction`, ADR-1) y se
cuantiza sólo al persistir.
"""
