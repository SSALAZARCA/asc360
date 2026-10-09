'use client';
/**
 * "Traslados" (Gestión repuestos): transfers between stores still alive in the ERP. KPIs, a per-store table and a
 * per-transfer detail with filters, reference lines and history. The Tienda que recibe / Estado / Antigüedad filters
 * apply to every section: the whole pending list is loaded once and filtered in memory.
 * `puedeConfirmar` (ADMIN, COORDINADOR_REPUESTOS and ANALISTA_ADMINISTRATIVO) adds the "Recibido" / "No ha llegado"
 * buttons; every other role reads. The container decides it from the role.
 */
import { useMemo, useRef, useState } from 'react';
import { fechaHoraBogota } from '../../../lib/motored/fechas';
import TrasladosKpis from './TrasladosKpis';
import TrasladosPorTienda from './TrasladosPorTienda';
import TrasladosDetalle from './TrasladosDetalle';
import FiltrosIngresos, { FILTROS_VACIOS } from './FiltrosIngresos';
import useTraslados from './useTraslados';
import { filtrarItems, tiendasDe } from './ingresosDerivados';
import { agruparTrasladosPorTienda, resumirTraslados } from './trasladosDerivados';
import { ESTADOS_FILTRO_TRASLADOS } from './trasladosEstilos';

function useFiltros(detalleRef) {
  const [filtros, setFiltros] = useState(FILTROS_VACIOS);
  const poner = (campo) => (valor) => setFiltros((f) => ({ ...f, [campo]: valor }));
  const elegirTienda = (id) => {
    const quitar = filtros.sucursal === id;
    setFiltros((f) => ({ ...f, sucursal: quitar ? '' : id }));
    if (!quitar) detalleRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  };
  return { filtros, poner, elegirTienda, limpiar: () => setFiltros(FILTROS_VACIOS) };
}

export default function TrasladosPanel({ puedeConfirmar = false }) {
  const { ultimaCarga, items, error, ocupada, confirmar } = useTraslados();
  const detalleRef = useRef(null);
  const { filtros, poner, elegirTienda, limpiar } = useFiltros(detalleRef);

  const visibles = useMemo(() => filtrarItems(items, filtros), [items, filtros]);
  const resumen = useMemo(() => resumirTraslados(visibles), [visibles]);
  const tiendasFila = useMemo(() => agruparTrasladosPorTienda(visibles), [visibles]);
  const tiendasOpciones = useMemo(() => tiendasDe(items), [items]);
  const filtrado = filtros.sucursal !== '' || filtros.estado !== null || filtros.edad !== FILTROS_VACIOS.edad;
  const sinDatos = ultimaCarga === null;

  return (
    <div style={{ maxWidth: '1240px', display: 'flex', flexDirection: 'column', gap: '22px' }}>
      <header style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <h1 style={{ margin: 0, fontSize: '30px', fontWeight: 700, letterSpacing: '-.02em' }}>Traslados</h1>
          <p style={{ margin: 0, fontSize: '14px' }}>
            Traslados entre puntos que siguen vivos en el ERP
            {ultimaCarga ? ` · última carga: ${fechaHoraBogota(ultimaCarga)}` : ''}
          </p>
        </div>
        {!sinDatos && (
          <FiltrosIngresos
            filtros={filtros} tiendas={tiendasOpciones} onCambiar={poner} onLimpiar={limpiar}
            estados={ESTADOS_FILTRO_TRASLADOS} etiquetaTienda="Tienda que recibe"
          />
        )}
      </header>

      {error && <p role="alert" style={{ margin: 0, fontSize: '13px', color: 'var(--motored-danger, #c0392b)' }}>{error}</p>}
      {sinDatos && <p style={{ margin: 0, fontSize: '15px' }}>Carga traslados para empezar el seguimiento</p>}

      {ultimaCarga && (
        <>
          <TrasladosKpis resumen={resumen} filtrado={filtrado} />
          <TrasladosPorTienda tiendas={tiendasFila} onElegir={elegirTienda} seleccionada={filtros.sucursal} />
          <div ref={detalleRef}>
            <TrasladosDetalle items={visibles} total={items.length} puedeConfirmar={puedeConfirmar} ocupada={ocupada} onConfirmar={confirmar} />
          </div>
          <p style={{ margin: 0, fontSize: '12.5px' }}>Los traslados salen del seguimiento cuando dejan de aparecer en el archivo de traslados (ya se recibieron en el ERP).</p>
        </>
      )}
    </div>
  );
}
