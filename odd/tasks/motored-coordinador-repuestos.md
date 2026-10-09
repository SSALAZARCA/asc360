# Motored: COORDINADOR_REPUESTOS role, "Gestión repuestos" section, ingreso store

## Objective
Supports the "Pedidos pendientes por ingresar" feature, which session `fe` owns: the cross service, the confirmations, the report section and the panel content. This session owns the role, the sidebar group with its route guard, and the ingreso store.

## Owner decisions (2026-10-08, given directly)
- **New role COORDINADOR_REPUESTOS.** It sees the "Gestión repuestos" section (the "Ingresos facturas" panel) AND the KPI's. It does not see Pedidos, Maestros, Configuración or Usuarios.
- **New sidebar group "Gestión repuestos" → "Ingresos facturas"**, for ADMIN, COMPRAS, GERENCIA and COORDINADOR_REPUESTOS.
- **The ingreso's C.O. fills `ingreso_factura.sucursal_id`**, matched on `sucursal.codigo_co`. An unknown C.O. leaves it NULL with no row error.

## Tasks
- [x] C1 (9b209f8, migration d7a3c5e91f20 on c7e1a4b92d36): the role. It needs a migration if the role is constrained in the DB. Update the role lists in `deps.py` / path rules / landing page / user admin role select, give it KPI access, and check `test_roles_sin_acceso`.
- [x] C2 (b7258b7): the sidebar group and the route guard for `/motored/gestion-repuestos/ingresos-facturas`, with a placeholder page that `fe` fills.
- [x] C3 (c87d050; backend 6630 passed, jest 2352 passed, PG18 upgrade chain OK): the C.O. → `sucursal_id` fill in the INGRESOS_FACTURAS ingest. This runs after "Volver a validar" lands.

## Sequencing
This starts after `motored-cargas-revalidar` lands, to keep a single writer.
