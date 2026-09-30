'use client';
/** Cases table (scrolls horizontally inside its container on tablet). */
import MotoredTableScroll from '../MotoredTableScroll';
import DetractoresRow from './DetractoresRow';

const thStyle = { padding: '0 12px 8px 0', textAlign: 'left', whiteSpace: 'nowrap' };
const HEADERS = [
  'No. caso', 'Fecha', 'Cliente', 'Placa', 'Centro', 'Satisfacción',
  'Autorizó datos', 'Estado', 'Responsable', 'Última acción',
];

export default function DetractoresTable({ casos, onOpen }) {
  return (
    <MotoredTableScroll>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
            {HEADERS.map((h) => <th key={h} style={thStyle}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {casos.map((c) => <DetractoresRow key={c.id} caso={c} onOpen={onOpen} />)}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}
