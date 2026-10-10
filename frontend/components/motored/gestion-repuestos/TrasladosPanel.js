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
import { PALETA } from './semaforo';

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

/** Rows the last load rejected are missing from the snapshot: their transfers would look received. */
function AvisoFilasConError({ cuantas }) {
  if (!(cuantas > 0)) return null;
  return (
    <p role="status" style={{ margin: 0, fontSize: '13.5px', fontWeight: 600, padding: '10px 14px', borderRadius: '10px', color: PALETA.atencion.ink, background: PALETA.atencion.soft, border: `1px solid ${PALETA.atencion.color}` }}>
      La última carga de traslados tuvo {cuantas} filas con error; esos traslados no aparecen aquí. Revísala en Maestros → Cargas.
    </p>
  );
}

export default function TrasladosPanel({ puedeConfirmar = false }) {
  const { ultimaCarga, filasConError, items, error, falloInicial, ocupada, confirmar, reintentar } = useTraslados();
  const detalleRef = useRef(null);
  const { filtros, poner, elegirTienda, limpiar } = useFiltros(detalleRef);

  const visibles = useMemo(() => filtrarItems(items, filtros), [items, filtros]);
  const resumen = useMemo(() => resumirTraslados(visibles), [visibles]);
  const tiendasFila = useMemo(() => agruparTrasladosPorTienda(visibles), [visibles]);
  const tiendasOpciones = useMemo(() => tiendasDe(items), [items]);
  const filtrado = filtros.sucursal !== '' || filtros.estado !== null || filtros.edad !== FILTROS_VACIOS.edad;
  const sinDatos = ultimaCarga === null;
  const hayCarga = Boolean(ultimaCarga);

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
        {hayCarga && (
          <FiltrosIngresos
            filtros={filtros} tiendas={tiendasOpciones} onCambiar={poner} onLimpiar={limpiar}
            estados={ESTADOS_FILTRO_TRASLADOS} etiquetaTienda="Tienda que recibe"
          />
        )}
      </header>

      {error && (
        <p role="alert" style={{ margin: 0, fontSize: '13px', color: 'var(--motored-danger, #c0392b)' }}>
          {error}
          {falloInicial && (
            <button type="button" onClick={reintentar} style={{ marginLeft: '10px', font: 'inherit', fontWeight: 700, cursor: 'pointer', textDecoration: 'underline', background: 'transparent', border: 0, color: 'inherit' }}>Reintentar</button>
          )}
        </p>
      )}
      {sinDatos && <p style={{ margin: 0, fontSize: '15px' }}>Carga traslados para empezar el seguimiento</p>}

      {hayCarga && (
        <>
          <AvisoFilasConError cuantas={filasConError} />
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
