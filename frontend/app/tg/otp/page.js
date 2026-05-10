'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { authFetch } from '../../../lib/authFetch';
import TgNav from '../../../components/tg/TgNav';
import VoiceInput from '../../../components/tg/VoiceInput';

export default function TgOtp() {
  const router = useRouter();
  const [user, setUser]       = useState(null);
  const [pending, setPending] = useState([]);
  const [loading, setLoading] = useState(true);
  const [plate, setPlate]     = useState('');
  const [orderId, setOrderId] = useState(null);
  const [code, setCode]       = useState('');
  const [step, setStep]       = useState('list'); // list | enter
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(null);
  const [error, setError]     = useState(null);

  useEffect(() => {
    const stored = sessionStorage.getItem('um_user');
    const token  = sessionStorage.getItem('um_token');
    if (!stored || !token) { router.replace('/tg'); return; }
    setUser(JSON.parse(stored));
    loadPending();
  }, []);

  const loadPending = async () => {
    setLoading(true);
    try {
      const res = await authFetch('/orders/pending-otp');
      if (res.status === 401) { router.replace('/tg'); return; }
      if (res.ok) setPending(await res.json());
    } finally {
      setLoading(false);
    }
  };

  const selectOrder = (o) => {
    setOrderId(o.order_id);
    setPlate(o.placa);
    setCode('');
    setError(null);
    setSuccess(null);
    setStep('enter');
  };

  const searchByPlate = async (plateOverride) => {
    const p = (plateOverride ?? plate).trim().toUpperCase();
    if (!p) return;
    setError(null);
    try {
      const res = await authFetch(`/orders/pending-otp/plate/${p}`);
      if (res.status === 404) { setError('Sin orden pendiente de firma para esa placa'); return; }
      if (!res.ok) { setError('Error al buscar'); return; }
      const data = await res.json();
      setOrderId(data.order_id);
      setPlate(p);
      setStep('enter');
    } catch (e) {
      setError(`Error: ${e.message}`);
    }
  };

  const submitOtp = async () => {
    if (!code.trim() || code.length !== 6) { setError('El código OTP debe tener 6 dígitos'); return; }
    setSubmitting(true);
    setError(null);
    try {
      const res = await authFetch(`/orders/${orderId}/otp/verify`, {
        method: 'POST',
        body: JSON.stringify({ code }),
      });
      if (res.ok) {
        const data = await res.json().catch(() => ({}));
        const phone = data.accepted_phone ? ` · Firmado desde ${data.accepted_phone}` : '';
        setSuccess(`Firma registrada correctamente.${phone} La moto queda marcada como entregada.`);
        setStep('list');
        loadPending();
      } else {
        const err = await res.json().catch(() => ({}));
        setError(err.detail || 'Código OTP incorrecto o expirado');
      }
    } catch (e) {
      setError(`Error: ${e.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const canBypass = ['superadmin', 'jefe_taller'].includes(user?.role);

  const submitBypass = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await authFetch(`/orders/${orderId}/otp/bypass`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json().catch(() => ({}));
        const who = data.bypass_by_name ? ` · Autorizado por ${data.bypass_by_name}` : '';
        setSuccess(`Firma registrada por bypass autorizado.${who} La moto queda marcada como entregada.`);
        setStep('list');
        loadPending();
      } else {
        const err = await res.json().catch(() => ({}));
        setError(err.detail || 'No se pudo realizar el bypass');
      }
    } catch (e) {
      setError(`Error: ${e.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: '#0a0a0c', paddingBottom: '5.5rem' }}>
      {/* Header */}
      <div style={{ background: '#13131a', borderBottom: '1px solid rgba(255,255,255,0.06)', padding: '0.9rem 1.25rem' }}>
        <p style={{ margin: 0, fontWeight: 900, fontSize: '0.9rem', color: '#fff' }}>Firma OTP</p>
        <p style={{ margin: 0, fontSize: '0.6rem', color: '#606075' }}>Registrar entrega de motocicleta</p>
      </div>

      <div style={{ padding: '1rem' }}>
        {/* Éxito */}
        {success && (
          <div style={{ padding: '0.85rem 1rem', background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.25)', borderRadius: 12, marginBottom: '0.75rem' }}>
            <p style={{ margin: 0, fontSize: '0.75rem', color: '#10b981', fontWeight: 700 }}>Firma exitosa</p>
            <p style={{ margin: '2px 0 0', fontSize: '0.65rem', color: '#606075' }}>{success}</p>
          </div>
        )}

        {step === 'list' && (
          <>
            {/* Búsqueda manual */}
            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', alignItems: 'center' }}>
              <input
                value={plate}
                onChange={e => setPlate(e.target.value.toUpperCase())}
                onKeyDown={e => e.key === 'Enter' && searchByPlate()}
                placeholder="Buscar por placa..."
                maxLength={6}
                style={{ flex: 1, background: '#13131a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10, padding: '0.65rem 0.9rem', color: '#fff', fontSize: '0.85rem', fontWeight: 700, letterSpacing: '0.06em', outline: 'none' }}
              />
              <VoiceInput
                onTranscript={text => {
                  const p = text.trim().toUpperCase().replace(/\s/g, '').slice(0, 6);
                  setPlate(p);
                  searchByPlate(p);
                }}
                onError={msg => setError(msg)}
                size={38}
              />
              <button onClick={searchByPlate} style={{ padding: '0.65rem 0.9rem', background: '#ff5f33', border: 'none', borderRadius: 10, color: '#fff', fontWeight: 800, fontSize: '0.82rem', cursor: 'pointer' }}>
                Buscar
              </button>
            </div>

            {/* Error */}
            {error && (
              <div style={{ padding: '0.65rem 0.9rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10, marginBottom: '0.75rem' }}>
                <p style={{ margin: 0, fontSize: '0.7rem', color: '#ef4444', fontWeight: 700 }}>{error}</p>
              </div>
            )}

            {/* Lista de pendientes */}
            {loading ? (
              <p style={{ color: '#606075', fontSize: '0.75rem', textAlign: 'center', padding: '2rem 0' }}>Cargando...</p>
            ) : pending.length === 0 ? (
              <p style={{ color: '#606075', fontSize: '0.75rem', textAlign: 'center', padding: '2rem 0' }}>Sin órdenes pendientes de firma</p>
            ) : (
              <>
                <p style={{ margin: '0 0 0.5rem', fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>Pendientes de firma</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  {pending.map(o => (
                    <div
                      key={o.order_id}
                      onClick={() => selectOrder(o)}
                      style={{ background: '#13131a', borderRadius: 12, padding: '0.85rem 1rem', border: '1px solid rgba(255,255,255,0.05)', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                    >
                      <div>
                        <p style={{ margin: 0, fontWeight: 900, fontSize: '1rem', color: '#ff8c5a' }}>{o.placa}</p>
                        <p style={{ margin: '2px 0 0', fontSize: '0.62rem', color: '#606075' }}>{o.cliente}</p>
                      </div>
                      <span style={{ fontSize: '0.62rem', color: '#f59e0b', fontWeight: 700, background: 'rgba(245,158,11,0.1)', padding: '3px 8px', borderRadius: 20, border: '1px solid rgba(245,158,11,0.2)' }}>Ingresar OTP →</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
        )}

        {step === 'enter' && (
          <div>
            <button
              onClick={() => { setStep('list'); setError(null); }}
              style={{ background: 'none', border: 'none', color: '#606075', fontSize: '0.75rem', cursor: 'pointer', padding: '0 0 0.75rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}
            >
              ← Volver
            </button>

            <div style={{ background: '#13131a', borderRadius: 14, padding: '1.25rem', border: '1px solid rgba(255,255,255,0.06)' }}>
              <p style={{ margin: '0 0 0.3rem', fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>Placa</p>
              <p style={{ margin: '0 0 1rem', fontWeight: 900, fontSize: '1.4rem', color: '#ff8c5a', letterSpacing: '0.06em' }}>{plate || '—'}</p>

              <p style={{ margin: '0 0 0.5rem', fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>Código OTP (6 dígitos)</p>
              <input
                value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="000000"
                inputMode="numeric"
                style={{ width: '100%', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 10, padding: '0.9rem 1rem', color: '#fff', fontSize: '1.5rem', fontWeight: 900, letterSpacing: '0.2em', textAlign: 'center', outline: 'none', boxSizing: 'border-box' }}
              />

              {error && (
                <p style={{ margin: '0.5rem 0 0', fontSize: '0.7rem', color: '#ef4444', fontWeight: 700 }}>{error}</p>
              )}

              <button
                onClick={submitOtp}
                disabled={submitting || code.length !== 6}
                style={{ width: '100%', marginTop: '1rem', padding: '0.9rem', background: '#ff5f33', border: 'none', borderRadius: 12, color: '#fff', fontWeight: 800, fontSize: '0.9rem', cursor: 'pointer', opacity: submitting || code.length !== 6 ? 0.5 : 1 }}
              >
                {submitting ? 'Verificando...' : 'Confirmar Firma'}
              </button>

              {canBypass && (
                <button
                  onClick={submitBypass}
                  disabled={submitting}
                  style={{ width: '100%', marginTop: '0.5rem', padding: '0.75rem', background: 'transparent', border: '1px solid rgba(245,158,11,0.35)', borderRadius: 12, color: '#f59e0b', fontWeight: 700, fontSize: '0.8rem', cursor: 'pointer', opacity: submitting ? 0.5 : 1 }}
                >
                  {submitting ? 'Procesando...' : 'Bypass autorizado (sin código)'}
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      <TgNav userRole={user?.role} />
    </div>
  );
}
