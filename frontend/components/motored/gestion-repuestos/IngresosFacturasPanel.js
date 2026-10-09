'use client';
/**
 * "Ingresos facturas" (Gestión repuestos): HMCL invoices still waiting for an
 * ingreso. KPIs, a per-store table and a per-invoice detail with filters and
 * history. The Tienda / Estado / Antigüedad filters apply to every section:
 * the whole pending list is loaded once and filtered in memory.
 * `puedeConfirmar` (ADMIN, COORDINADOR_REPUESTOS and ANALISTA_ADMINISTRATIVO) adds the
 * "Llegó" / "No ha llegado" buttons and `puedeDescargar` (ADMIN and
 * ANALISTA_ADMINISTRATIVO) the "Descargar plantilla" link; every other role reads. The page that mounts it decides it from the role.
 */
import { useMemo, useRef, useState } from 'react';
import { fechaBogota } from '../../../lib/motored/fechas';
import IngresosKpis from './IngresosKpis';
import IngresosPorTienda from './IngresosPorTienda';
import IngresosDetalle from './IngresosDetalle';
import FiltrosIngresos, { FILTROS_VACIOS } from './FiltrosIngresos';
import useIngresosPendientes from './useIngresosPendientes';
import { agruparPorTienda, filtrarItems, resumir, tiendasDe } from './ingresosDerivados';
import { LeyendaSemaforo } from './SemaforoUi';

export default function IngresosFacturasPanel({ puedeConfirmar = false, puedeDescargar = false }) {
  const { desde, items, error, ocupada, confirmar } = useIngresosPendientes();
  const [filtros, setFiltros] = useState(FILTROS_VACIOS);
  const detalleRef = useRef(null);

  const poner = (campo) => (valor) => setFiltros((f) => ({ ...f, [campo]: valor }));
  const elegirTienda = (id) => {
    const quitar = filtros.sucursal === id;
    setFiltros((f) => ({ ...f, sucursal: quitar ? '' : id }));
    if (!quitar) detalleRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  };

  const visibles = useMemo(() => filtrarItems(items, filtros), [items, filtros]);
  const resumen = useMemo(() => resumir(visibles), [visibles]);
  const tiendasFila = useMemo(() => agruparPorTienda(visibles), [visibles]);
  const tiendasOpciones = useMemo(() => tiendasDe(items), [items]);
  const filtrado = filtros.sucursal !== '' || filtros.estado !== null || filtros.edad !== FILTROS_VACIOS.edad;
  const sinDatos = desde === null;

  return (
    <div style={{ maxWidth: '1240px', display: 'flex', flexDirection: 'column', gap: '22px' }}>
      <header style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <h1 style={{ margin: 0, fontSize: '30px', fontWeight: 700, letterSpacing: '-.02em' }}>Ingresos facturas</h1>
          <p style={{ margin: 0, fontSize: '14px' }}>
            Seguimiento de facturas de pedido pendientes por ingresar
            {desde ? ` · Verificable desde el ${fechaBogota(desde)}` : ''}
          </p>
        </div>
        {!sinDatos && (
          <FiltrosIngresos
            filtros={filtros} tiendas={tiendasOpciones} onCambiar={poner} onLimpiar={() => setFiltros(FILTROS_VACIOS)}
          />
        )}
        {!sinDatos && <LeyendaSemaforo />}
      </header>

      {error && <p role="alert" style={{ margin: 0, fontSize: '13px', color: 'var(--motored-danger, #c0392b)' }}>{error}</p>}

      {sinDatos && (
        <p style={{ margin: 0, fontSize: '15px' }}>Carga ingresos de facturas para empezar el seguimiento</p>
      )}

      {desde && (
        <>
          <IngresosKpis resumen={resumen} filtrado={filtrado} />
          <IngresosPorTienda tiendas={tiendasFila} onElegir={elegirTienda} seleccionada={filtros.sucursal} />
          <div ref={detalleRef}>
            <IngresosDetalle
              items={visibles} total={items.length} cargando={false}
              puedeConfirmar={puedeConfirmar} puedeDescargar={puedeDescargar} ocupada={ocupada} onConfirmar={confirmar}
            />
          </div>
          <p style={{ margin: 0, fontSize: '12.5px' }}>Las facturas salen del seguimiento cuando aparecen en Ingresos de facturas.</p>
        </>
      )}
    </div>
  );
}
