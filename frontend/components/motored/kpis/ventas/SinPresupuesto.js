import Link from 'next/link';
import { COLOR } from '../tokens';

/** Empty state of every compliance card when no budget is loaded for the selection. */
export default function SinPresupuesto() {
  return (
    <p style={{ margin: '14px 0 0', fontSize: 13.5 }}>
      <Link href="/motored/maestros" style={{ color: COLOR.info }}>Cargá los presupuestos en Maestros → Presupuestos</Link>
    </p>
  );
}
