'use client';
/** Case detail screen: composes header, warning, cards, log and controls. */
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import useDetractoresGate from '../../../lib/motored/useDetractoresGate';
import useDetractorDetail from './useDetractorDetail';
import DetalleHeader from './DetalleHeader';
import ConsentWarning from './ConsentWarning';
import ClienteCard from './ClienteCard';
import RespuestaCard from './RespuestaCard';
import Historial from './Historial';
import AccionForm from './AccionForm';
import EstadoControls from './EstadoControls';
import { errorStyle, gridStyle } from './styles';

function LoadError({ message }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', alignItems: 'flex-start' }}>
      <div role="alert" style={errorStyle}>{message}</div>
      <Link href="/motored/detractores" className="motored-btn motored-btn-secondary">Volver a detractores</Link>
    </div>
  );
}

export default function DetractorDetailContainer() {
  const { id } = useParams();
  const router = useRouter();
  const allowed = useDetractoresGate();
  const d = useDetractorDetail(id, allowed);
  if (!allowed) return null;
  if (d.loadError && !d.caso) return <LoadError message={d.loadError} />;
  if (!d.caso) return <p style={{ margin: 0, fontSize: '0.8rem' }}>Cargando...</p>;
  const { caso } = d;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '100%' }}>
      <DetalleHeader caso={caso} onBack={() => router.push('/motored/detractores')} />
      {caso.autoriza_datos === false && <ConsentWarning />}
      <div style={gridStyle}>
        <ClienteCard registro={caso.registro} />
        <RespuestaCard respuesta={caso.respuesta} />
      </div>
      <Historial acciones={caso.acciones} />
      <div style={gridStyle}>
        <AccionForm estado={caso.estado} error={d.accionError} busy={d.busy} onSubmit={d.registrarAccion} />
        <EstadoControls estado={caso.estado} error={d.estadoError} busy={d.busy} onSubmit={d.cambiarEstado} />
      </div>
    </div>
  );
}
