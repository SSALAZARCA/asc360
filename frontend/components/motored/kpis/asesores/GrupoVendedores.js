import { StackedBar100 } from '../charts';
import { millones, pct } from '../format';
import { COLOR } from '../tokens';
import { NUM, TARJETA, TITULO } from '../ventas/estilos';
import { ventaPorGrupo } from './datos';

/** "Venta por grupo de vendedores": asesores, comerciales, other roles and the rest of the company. */
export default function GrupoVendedores({ data }) {
  const grupos = ventaPorGrupo(data);
  const total = grupos.reduce((t, g) => t + g.value, 0);
  return (
    <section aria-label="Venta por grupo de vendedores" style={TARJETA}>
      <h2 style={TITULO}>Venta por grupo de vendedores</h2>
      <div style={{ marginTop: 16 }}><StackedBar100 segments={grupos} height={16} /></div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginTop: 10, fontSize: 12.5, color: COLOR.ink2 }}>
        {grupos.map((g) => (
          <span key={g.label} data-testid="grupo-leyenda" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 10, height: 10, borderRadius: 3, background: g.color }} />
            {g.label}
            <strong style={NUM}>{millones(g.value)}</strong>
            <span style={NUM}> · {pct(total > 0 ? g.value / total : null)}</span>
          </span>
        ))}
      </div>
    </section>
  );
}
