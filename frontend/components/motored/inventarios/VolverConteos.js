'use client';
/** "← Volver a conteos" (or "← Volver al panel" with `onClick`). */
import { useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { CONTEOS_PATH } from '../../../lib/motored/session';

export default function VolverConteos({ onClick, texto = 'Volver a conteos' }) {
  const router = useRouter();
  return (
    <button
      type="button" className="motored-btn motored-btn-tertiary" style={{ alignSelf: 'flex-start', minHeight: '44px' }}
      onClick={onClick || (() => router.push(CONTEOS_PATH))}
    >
      <ArrowLeft size={14} /> {texto}
    </button>
  );
}
