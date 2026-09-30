"""
Motored Pedidos F3 "Motor" (S8b) — regresión contra el Excel, niveles A, B y
C, y exportación de corridas a Excel para el dueño.

    cd backend
    python scripts/motored_regresion.py --help

Los subcomandos (`nivel-a`, `nivel-b`, `delta`, `exportar-corrida`) están en
`app.motored.herramientas.regresion.comandos`; ver `docs/motored/
regresion_f3.md`. Todo informe se escribe fuera del repositorio.
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.motored.herramientas.regresion.comandos import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
