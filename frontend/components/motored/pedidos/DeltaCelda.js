/** A difference (scenario minus real) as sign + arrow + number, so it never depends on colour alone (UX-31). */
import { ArrowDown, ArrowUp, Minus } from 'lucide-react';
import { formatCOP } from '../../../lib/motored/formatCOP';
import { deltaConSigno, deltaCOP, direccionDelta, unidades } from './formato';

const ICONOS = { sube: ArrowUp, baja: ArrowDown, igual: Minus };
const VERBOS = { sube: 'Sube', baja: 'Baja' };

function titulo(valor, moneda) {
  const direccion = direccionDelta(valor);
  if (direccion === 'igual') return 'Sin cambio frente a la corrida real';
  const magnitud = Math.abs(Number(valor));
  const cantidad = moneda ? formatCOP(magnitud) : `${unidades(magnitud)} ${magnitud === 1 ? 'unidad' : 'unidades'}`;
  return `${VERBOS[direccion]} ${cantidad} frente a la corrida real`;
}

export default function DeltaCelda({ valor, moneda = false, sufijo = '' }) {
  const direccion = direccionDelta(valor);
  const Icono = ICONOS[direccion];
  const texto = moneda ? deltaCOP(valor) : deltaConSigno(valor);
  return (
    <span
      data-direccion={direccion} title={titulo(valor, moneda)}
      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', fontWeight: direccion === 'igual' ? 400 : 700 }}
    >
      <Icono size={14} aria-hidden="true" />
      {`${texto}${sufijo}`}
    </span>
  );
}
