'use client';
/**
 * Public asesor report (no session, not wrapped in MotoredLayout). The cédula lives only in this
 * component's state while the request runs; nothing is written to storage or cookies, so a reload asks again.
 */
import { useState } from 'react';
import Image from 'next/image';
import { verInforme } from '../../../lib/motored/informeApi';
import AsesorDetalle from '../kpis/asesores/AsesorDetalle';
import CedulaForm from './CedulaForm';

function Cabecera() {
  return (
    <header style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', background: 'var(--motored-surface)', borderBottom: '1px solid var(--motored-border)' }}>
      <Image src="/motored-logo.png" alt="Motored" width={120} height={40} style={{ height: 36, width: 'auto' }} priority />
    </header>
  );
}

export default function InformeContainer({ token }) {
  const [data, setData] = useState(null);
  const [cedulaUsada, setCedulaUsada] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const consultar = async (cedula) => {
    setLoading(true);
    setError('');
    try {
      setData(await verInforme(token, cedula));
      setCedulaUsada(cedula);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh' }}>
      <Cabecera />
      <main style={{ padding: '24px 16px', maxWidth: 1100, margin: '0 auto' }}>
        {data ? <AsesorDetalle data={data} enlace={{ token, cedula: cedulaUsada }} /> : <CedulaForm onSubmit={consultar} loading={loading} serverError={error} />}
      </main>
    </div>
  );
}
