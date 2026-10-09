"""
Motored physical inventory counts (odd/motored-conteos-inventario).

- `snapshot`: schedule, reschedule, annul and start a count (the frozen
  copy of the store's inventory);
- `acceso`: the pair link slug and the rotating 6-digit code;
- `sesiones`: pair device sessions; `consultas`: the leader's reads;
- `ubicaciones`, `lecturas`, `catalogo`: the store's locations, the
  pairs' readings and the referencia master they download;
- `diferencias`, `reconteos`: the leader-only differences (one aggregate,
  the final-quantity rule) and the reconteo round;
- `cierre`, `excel_ajustes`: the close (result lines, accuracy KPI) and
  the ERP adjustment Excel;
- `panel`: the leader's live panel (version short-circuit, progress,
  partial accuracy, readings per pair);
- `errores`: the domain errors the API maps to HTTP.
"""
