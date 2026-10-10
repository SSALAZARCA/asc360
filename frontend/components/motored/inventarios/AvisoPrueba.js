'use client';
/**
 * Band on top of every screen of a TEST conteo (odd/tasks/motored-conteo-prueba.md): the PRUEBA badge, a reminder
 * that it never goes to the ERP and, for ADMIN, "Borrar conteo de prueba" (any estado) with its confirmation.
 */
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { CONTEOS_PATH } from '../../../lib/motored/session';
import { avisoStyle } from './estilos';
import BorrarPruebaDialog from './BorrarPruebaDialog';
import PruebaBadge from './PruebaBadge';

export default function AvisoPrueba({ conteo, administra }) {
  const router = useRouter();
  const [borrando, setBorrando] = useState(false);
  return (
    <div style={{ ...avisoStyle('warning'), alignItems: 'center', flexWrap: 'wrap', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', flexWrap: 'wrap', minWidth: 0 }}>
        <PruebaBadge />
        <span>Conteo de prueba: solo lo ve el administrador y su Excel no se carga al ERP.</span>
      </div>
      {administra && (
        <button
          type="button" className="motored-btn motored-btn-secondary" style={{ minHeight: '44px' }}
          onClick={() => setBorrando(true)}
        >
          Borrar conteo de prueba
        </button>
      )}
      {borrando && (
        <BorrarPruebaDialog conteo={conteo} onCancel={() => setBorrando(false)} onListo={() => router.push(CONTEOS_PATH)} />
      )}
    </div>
  );
}
