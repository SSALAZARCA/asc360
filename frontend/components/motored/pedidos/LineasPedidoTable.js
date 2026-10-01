'use client';
/** Lines of a tienda pedido. Scrolls inside its box; code column and header stay in view. */
import InfoTooltip from '../InfoTooltip';
import MotoredTableScroll from '../MotoredTableScroll';
import LineaFila from './LineaFila';
import { stickyColStyle, stickyHeadStyle, tablaStyle, thCompactStyle as thStyle } from './styles';

const COLUMNAS = [
  ['Código'], ['Nombre'],
  ['Clase', 'Clase: clasificación de la referencia por importancia (A, B, C, D) y rotación (F, M, S).'],
  ['Empaque', 'Empaque: unidades por paquete. Conviene pedir en múltiplos de este número.'],
  ['Precio'],
  ['Sugerido', 'Sugerido: cantidad que calculó el motor. No se puede cambiar.'],
  ['Cantidad a pedir', 'Cantidad a pedir: lo que se va a mandar a HMCL. Empieza igual al sugerido y el comprador la ajusta.'],
  ['Valor', 'Valor: cantidad a pedir por el precio de la referencia.'],
  ['Quiebre', 'Quiebre: situación de inventario de la referencia (normal, bajo mínimo, sobrestock, sin existencias).'],
];

function Encabezado({ titulo, ayuda, pegada }) {
  return (
    <th style={{ ...thStyle, ...stickyHeadStyle, ...(pegada ? { ...stickyColStyle, zIndex: 4, top: 0 } : {}) }}>
      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
        {titulo}
        {ayuda && <InfoTooltip text={ayuda} />}
      </span>
    </th>
  );
}

export default function LineasPedidoTable({ lineas, edicion, onHistorial, recortes }) {
  return (
    <MotoredTableScroll maxHeight="70vh">
      <table aria-label="Líneas del pedido" style={{ ...tablaStyle, width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
            {COLUMNAS.map(([titulo, ayuda], i) => <Encabezado key={titulo} titulo={titulo} ayuda={ayuda} pegada={i === 0} />)}
          </tr>
        </thead>
        <tbody>
          {lineas.map((l) => <LineaFila key={l.id} linea={l} edicion={edicion} onHistorial={onHistorial} recorte={recortes && recortes[l.id]} />)}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}
