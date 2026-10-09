'use client';
import { tarjeta, tituloSeccion, subtitulo, tabla, th, td } from './ingresosEstilos';
import { AMBAR } from './trasladosEstilos';
import { nivelPorDias } from './semaforo';
import { PildoraNivel } from './SemaforoUi';

/** Most "recibidos sin cargar al ERP" first, then most pending. */
export function ordenarTiendasTraslados(tiendas) {
  return [...(tiendas || [])].sort((a, b) => (
    (b.recibidos_sin_erp - a.recibidos_sin_erp) || (b.pendientes - a.pendientes)
    || String(a.tienda).localeCompare(String(b.tienda), 'es')));
}

function Fila({ t, seleccionada, onElegir }) {
  return (
    <tr
      onClick={() => onElegir(t.sucursal_id)}
      style={{ cursor: 'pointer', ...(seleccionada ? { background: 'var(--motored-surface-alt, #eef3f9)', outline: '2px solid #1d4e89', outlineOffset: '-2px' } : {}) }}
      tabIndex={0} aria-selected={seleccionada}
      onKeyDown={(e) => { if (e.key === 'Enter') onElegir(t.sucursal_id); }}
      title={seleccionada ? `Quitar el filtro de ${t.tienda}` : `Ver el detalle de ${t.tienda}`}
    >
      <td style={{ ...td(true), fontWeight: 700 }}>{t.tienda}</td>
      <td style={td()}>{t.pendientes}</td>
      <td style={t.recibidos_sin_erp > 0 ? { ...td(), fontWeight: 700, color: AMBAR.tinta } : td()}>{t.recibidos_sin_erp}</td>
      <td style={td()}>{t.sin_confirmar}</td>
      <td style={td()}>{t.aun_no_llegan}</td>
      <td style={td()}><PildoraNivel nivel={nivelPorDias(t.mas_antiguo_dias)}>{t.mas_antiguo_dias ?? '—'}</PildoraNivel></td>
      <td style={td()}>{t.unidades}</td>
    </tr>
  );
}

export default function TrasladosPorTienda({ tiendas, onElegir, seleccionada = '' }) {
  return (
    <section style={{ ...tarjeta, display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div>
        <h2 style={tituloSeccion}>Por tienda</h2>
        <p style={subtitulo}>Tienda que recibe, ordenado por recibidos sin cargar al ERP · toca una tienda para ver su detalle</p>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table aria-label="Por tienda" style={{ ...tabla, minWidth: '760px' }}>
          <thead>
            <tr>
              <th scope="col" style={th(true)}>Tienda</th>
              <th scope="col" style={th()}>Pendientes</th>
              <th scope="col" style={{ ...th(), color: AMBAR.tinta }}>Recibidos sin cargar</th>
              <th scope="col" style={th()}>Sin confirmar</th>
              <th scope="col" style={th()}>Aún no llega</th>
              <th scope="col" style={th()} title="Días desde la fecha del traslado más antiguo pendiente">Más antiguo (días)</th>
              <th scope="col" style={th()}>Unidades</th>
            </tr>
          </thead>
          <tbody>
            {ordenarTiendasTraslados(tiendas).map((t) => (
              <Fila key={t.sucursal_id} t={t} seleccionada={t.sucursal_id === seleccionada} onElegir={onElegir} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
