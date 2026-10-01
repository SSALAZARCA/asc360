'use client';
/** Cap banner of the corrida detail: how many tiendas are above their cap (nothing while the mode is off). */
import { plural } from './formato';
import { topeBannerStyle } from './styles';
import { contarSobreTope } from './tope';

export default function TopeResumenCorrida({ topes }) {
  if (!topes || !topes.activo) return null;
  const n = contarSobreTope(topes.tiendas);
  const texto = n > 0
    ? `${n} ${plural(n, 'tienda supera', 'tiendas superan')} su tope de presupuesto.`
    : 'Ninguna tienda supera su tope de presupuesto.';
  return (
    <div role="status" aria-label="Tope de presupuesto" style={{ ...topeBannerStyle, fontSize: '0.85rem', fontWeight: 600 }}>
      {`Modo tope activo: ${texto}`}
    </div>
  );
}
