import InfoTooltip from '../../InfoTooltip';
import { millones, pct } from '../format';
import { CATEGORIA, COLOR } from '../tokens';
import { NUM } from './estilos';

const TIP_GRUPOS = 'Cómo se reparte la venta total de la compañía entre los grupos de vendedores. Los cuatro suman el valor del medidor.';
const TIP_ASESORES = 'Venta de los asesores de repuestos contra sus propios presupuestos; solo ellos tienen presupuesto asignado.';

/** Compact split of the company sales by seller group, under the gauge. */
export default function VentaPorGrupo({ compania }) {
  const grupos = compania.por_grupo ?? [];
  const asesores = compania.asesores;
  return (
    <section aria-label="Venta por grupo de vendedores" style={{ alignSelf: 'stretch', marginTop: 14, fontSize: 12.5, color: COLOR.muted }}>
      <div style={{ fontWeight: 600, color: COLOR.ink2, marginBottom: 6 }}>
        Venta por grupo <InfoTooltip text={TIP_GRUPOS} />
      </div>
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {grupos.map((g, i) => (
          <li key={g.grupo} data-testid="grupo-fila">
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <span>{g.grupo}</span>
              <span style={NUM}><strong style={{ color: COLOR.ink }}>{millones(g.venta)}</strong> · {pct(g.pct)}</span>
            </div>
            <div style={{ height: 4, borderRadius: 999, background: COLOR.track, marginTop: 3 }}>
              <div style={{ width: `${Math.min(100, Math.max(0, (g.pct ?? 0) * 100))}%`, height: '100%', borderRadius: 999, background: CATEGORIA[i % CATEGORIA.length] }} />
            </div>
            {i === 0 && asesores?.presupuesto > 0 && (
              <div data-testid="asesores-cumplimiento" style={{ marginTop: 3, ...NUM }}>
                {millones(asesores.venta_cumplimiento)} de {millones(asesores.presupuesto)} · {pct(asesores.cumplimiento_pct)} <InfoTooltip text={TIP_ASESORES} />
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
