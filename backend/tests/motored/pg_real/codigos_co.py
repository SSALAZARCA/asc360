"""
Store codes (C.O.) for the `pg_real` seeds.

`sucursal.codigo_co` is NOT NULL and UNIQUE, and a code is one letter plus
two digits (2600 values). `codigo_co_unico()` walks every value once per
cycle from a random start, so the codes of one test never repeat, and the
seeds of a test do not depend on which tests ran before it (each test
rolls back or deletes what it committed).
"""
import itertools
import random
import string

_TODOS = [
    letra + f"{numero:02d}"
    for letra in string.ascii_uppercase for numero in range(100)
]
_INICIO = random.randrange(len(_TODOS))
_SIGUIENTE = itertools.cycle(_TODOS[_INICIO:] + _TODOS[:_INICIO])


def codigo_co_unico() -> str:
    """The next well-formed store code of this process."""
    return next(_SIGUIENTE)
