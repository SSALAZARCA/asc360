'use client';
/** The six KPI cards at the top of the Inventario tab. */
import { COLOR } from '../tokens';
import { NUM, ROTULO, TARJETA } from '../ventas/estilos';
import { tarjetas } from './datos';

export default function TarjetasInventario({ data }) {
  return (
    <div className="inv-tiles">
      {tarjetas(data).map((k) => (
        <div key={k.id} data-testid="tarjeta-inv" title={k.tip} style={{ ...TARJETA, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <p style={ROTULO}>{k.label}</p>
          <p style={{ ...NUM, fontSize: 24, fontWeight: 700, color: k.color, margin: '6px 0 0', letterSpacing: '-.01em' }}>{k.value}</p>
          {k.sub && <span style={{ fontSize: 12, color: COLOR.muted }}>{k.sub}</span>}
        </div>
      ))}
    </div>
  );
}
