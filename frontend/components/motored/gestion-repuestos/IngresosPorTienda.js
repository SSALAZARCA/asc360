'use client';
import { formatCOP } from '../../../lib/motored/formatCOP';
import { tarjeta, tituloSeccion, subtitulo, tabla, th, td } from './ingresosEstilos';
import { PALETA, CRITICO, nivelPorDias, nivelTienda } from './semaforo';
import { PildoraNivel, PuntoNivel } from './SemaforoUi';

/** Most "llegaron sin ingresar" first, then most pending. */
export function ordenarTiendas(tiendas) {
  return [...(tiendas || [])].sort((a, b) => (
    (b.llegaron_sin_ingresar - a.llegaron_sin_ingresar) || (b.pendientes - a.pendientes)
    || String(a.tienda).localeCompare(String(b.tienda), 'es')));
}

export default function IngresosPorTienda({ tiendas, onElegir }) {
  return (
    <section style={{ ...tarjeta, display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div>
        <h2 style={tituloSeccion}>Por tienda</h2>
        <p style={subtitulo}>Ordenado por facturas que llegaron sin ingresar · toca una tienda para ver su detalle</p>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table aria-label="Por tienda" style={{ ...tabla, minWidth: '760px' }}>
          <thead>
            <tr>
              <th scope="col" style={th(true)}>Tienda</th>
              <th scope="col" style={th()}>Pendientes</th>
              <th scope="col" style={{ ...th(), color: PALETA[CRITICO].ink }}>Llegaron sin ingresar</th>
              <th scope="col" style={th()}>Sin confirmar</th>
              <th scope="col" style={th()}>Aún no llega</th>
              <th scope="col" style={th()} title="Días desde la fecha de la factura más antigua pendiente">Más antigua (días)</th>
              <th scope="col" style={th()}>Valor pendiente</th>
            </tr>
          </thead>
          <tbody>
            {ordenarTiendas(tiendas).map((t) => (
              <tr
                key={t.sucursal_id} onClick={() => onElegir(t.sucursal_id)} style={{ cursor: 'pointer' }}
                tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter') onElegir(t.sucursal_id); }}
                title={`Ver el detalle de ${t.tienda}`}
              >
                <td style={{ ...td(true), fontWeight: 700 }}><PuntoNivel nivel={nivelTienda(t)} />{t.tienda}</td>
                <td style={td()}>{t.pendientes}</td>
                <td style={t.llegaron_sin_ingresar > 0 ? { ...td(), fontWeight: 700, color: PALETA[CRITICO].ink } : td()}>{t.llegaron_sin_ingresar}</td>
                <td style={td()}>{t.sin_confirmar}</td>
                <td style={td()}>{t.aun_no_llegan}</td>
                <td style={td()}><PildoraNivel nivel={nivelPorDias(t.mas_antigua)}>{t.mas_antigua ?? '—'}</PildoraNivel></td>
                <td style={td()}>{formatCOP(t.valor_pendiente)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
