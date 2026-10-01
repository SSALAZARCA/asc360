'use client';
/**
 * Scenario vs real corrida, one row per tienda and reference: the suggested
 * quantity of each side and the change. The tienda column stays in view while
 * the table scrolls sideways on a tablet.
 */
import InfoTooltip from '../InfoTooltip';
import MotoredTableScroll from '../MotoredTableScroll';
import DeltaCelda from './DeltaCelda';
import { claseTexto, pedidoRealTexto } from './comparacion';
import { unidades } from './formato';
import { numStyle, stickyColStyle, stickyHeadStyle, tablaStyle, tdCompactStyle, thCompactStyle } from './styles';

const REAL_TEXTO = 'Real: lo que el sistema sugiere pedir en la corrida real, antes de los ajustes de Compras.';
const PRUEBA_TEXTO = 'Prueba: lo que sugiere pedir el escenario con los parámetros que se están probando.';
const CAMBIO_TEXTO = 'Cambio: prueba menos real. Con + el escenario pide más; con - pide menos.';
const CLASE_TEXTO = 'Clase: la letra con la que se clasifica la referencia. Si el escenario la cambia se ve así: real → prueba.';

function Encabezado({ texto, ayuda, pegada }) {
  const base = { ...thCompactStyle, ...stickyHeadStyle, ...(pegada ? { ...stickyColStyle, zIndex: 4, top: 0 } : {}) };
  return (
    <th style={base}>
      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
        {texto}
        {ayuda && <InfoTooltip text={ayuda} />}
      </span>
    </th>
  );
}

const izquierda = { textAlign: 'left', whiteSpace: 'normal' };
const muted = { fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' };

function Fila({ fila }) {
  const pedido = pedidoRealTexto(fila);
  return (
    <tr style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
      <td style={{ ...tdCompactStyle, ...stickyColStyle, ...izquierda, fontWeight: 600 }}>{fila.sucursal}</td>
      <td style={{ ...tdCompactStyle, ...izquierda }}>
        <strong>{fila.codigo}</strong>
        <div style={muted}>{fila.nombre}</div>
      </td>
      <td style={tdCompactStyle}>{claseTexto(fila)}</td>
      <td style={{ ...tdCompactStyle, ...numStyle }}>
        {unidades(fila.sugerido_real)}
        {pedido && <div style={muted}>{pedido}</div>}
      </td>
      <td style={{ ...tdCompactStyle, ...numStyle }}>{unidades(fila.sugerido_prueba)}</td>
      <td style={{ ...tdCompactStyle, ...numStyle }}><DeltaCelda valor={fila.delta} /></td>
    </tr>
  );
}

export default function ComparacionTable({ filas }) {
  return (
    <MotoredTableScroll maxHeight="70vh">
      <table aria-label="Comparación con la corrida real" style={{ ...tablaStyle, width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
            <Encabezado texto="Tienda" pegada />
            <Encabezado texto="Referencia" />
            <Encabezado texto="Clase" ayuda={CLASE_TEXTO} />
            <Encabezado texto="Real" ayuda={REAL_TEXTO} />
            <Encabezado texto="Prueba" ayuda={PRUEBA_TEXTO} />
            <Encabezado texto="Cambio" ayuda={CAMBIO_TEXTO} />
          </tr>
        </thead>
        <tbody>
          {filas.map((f) => <Fila key={`${f.sucursal_id}-${f.referencia_id}`} fila={f} />)}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}
