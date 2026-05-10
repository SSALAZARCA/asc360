'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { authFetch } from '../../../lib/authFetch';
import TgNav from '../../../components/tg/TgNav';

const SERVICE_TYPES = [
  { value: 'regular',   label: 'Mecánica General' },
  { value: 'km_review', label: 'Revisión por KM' },
  { value: 'warranty',  label: 'Garantía' },
  { value: 'pdi',       label: 'Alistamiento (PDI)' },
];

const GAS_LEVELS = ['Vacío', 'Reserva', '1/4', '1/2', '3/4', 'Lleno'];

const STEPS = ['placa', 'tipo', 'recepcion', 'confirmar'];

export default function TgReception() {
  const router = useRouter();
  const [user, setUser]     = useState(null);
  const [step, setStep]     = useState(0);
  const [plate, setPlate]   = useState('');
  const [vehicle, setVehicle] = useState(null);
  const [lookupError, setLookupError] = useState(null);
  const [looking, setLooking] = useState(false);

  const [serviceType, setServiceType] = useState('regular');
  const [km, setKm]         = useState('');
  const [gas, setGas]       = useState('');
  const [notes, setNotes]   = useState('');
  const [accessories, setAccessories] = useState('');
  const [observations, setObservations] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [submitted, setSubmitted]   = useState(null);

  useEffect(() => {
    const stored = sessionStorage.getItem('um_user');
    const token  = sessionStorage.getItem('um_token');
    if (!stored || !token) { router.replace('/tg'); return; }
    setUser(JSON.parse(stored));
  }, []);

  const lookupVehicle = async () => {
    if (!plate.trim()) return;
    setLooking(true);
    setLookupError(null);
    setVehicle(null);
    try {
      const res = await authFetch(`/vehicles/${plate.trim().toUpperCase()}`);
      if (res.status === 401) { router.replace('/tg'); return; }
      if (res.status === 404) { setLookupError('Vehículo no registrado en el sistema'); return; }
      if (!res.ok) { setLookupError('Error al consultar la placa'); return; }
      const data = await res.json();
      if (data.active_order) { setLookupError('Este vehículo ya tiene una orden activa en taller'); return; }
      setVehicle(data);
      setStep(1);
    } catch (e) {
      setLookupError(`Error: ${e.message}`);
    } finally {
      setLooking(false);
    }
  };

  const submit = async () => {
    if (!km || !gas) { setSubmitError('Completá KM y nivel de gasolina'); return; }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const tenantId = vehicle.tenant_id || user.tenant_id;
      if (!tenantId) { setSubmitError('No se pudo determinar el taller'); return; }

      const body = {
        tenant_id: tenantId,
        vehicle_id: vehicle.id,
        client_id: vehicle.client_id || null,
        service_type: serviceType,
        reception: {
          mileage_km: parseFloat(km),
          gas_level: gas,
          customer_notes: notes || null,
          accessories: accessories ? accessories.split(',').map(a => a.trim()).filter(Boolean) : [],
          general_observations: observations || null,
          damage_photos_urls: [],
          intake_answers: [],
          warranty_warnings: null,
        },
      };

      const res = await authFetch('/orders/', { method: 'POST', body: JSON.stringify(body) });
      if (res.status === 401) { router.replace('/tg'); return; }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setSubmitError(err.detail || 'Error al crear la orden');
        return;
      }
      const order = await res.json();
      setSubmitted(order);
    } catch (e) {
      setSubmitError(`Error: ${e.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const reset = () => {
    setStep(0); setPlate(''); setVehicle(null); setLookupError(null);
    setServiceType('regular'); setKm(''); setGas(''); setNotes('');
    setAccessories(''); setObservations(''); setSubmitted(null); setSubmitError(null);
  };

  const card = (content) => (
    <div style={{ background: '#13131a', borderRadius: 14, padding: '1.25rem', border: '1px solid rgba(255,255,255,0.06)' }}>
      {content}
    </div>
  );

  return (
    <div style={{ minHeight: '100vh', background: '#0a0a0c', paddingBottom: '5.5rem' }}>
      {/* Header */}
      <div style={{ background: '#13131a', borderBottom: '1px solid rgba(255,255,255,0.06)', padding: '0.9rem 1.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        {step > 0 && !submitted && (
          <button onClick={() => setStep(s => s - 1)} style={{ background: 'none', border: 'none', color: '#606075', cursor: 'pointer', fontSize: '1rem', padding: 0 }}>←</button>
        )}
        <div>
          <p style={{ margin: 0, fontWeight: 900, fontSize: '0.9rem', color: '#fff' }}>Nueva Recepción</p>
          <p style={{ margin: 0, fontSize: '0.6rem', color: '#606075' }}>
            {submitted ? 'Completado' : `Paso ${step + 1} de ${STEPS.length}: ${['Placa','Tipo de Servicio','Datos de Ingreso','Confirmar'][step]}`}
          </p>
        </div>
      </div>

      {/* Indicador de pasos */}
      {!submitted && (
        <div style={{ display: 'flex', gap: '0.3rem', padding: '0.75rem 1rem 0' }}>
          {STEPS.map((_, i) => (
            <div key={i} style={{ flex: 1, height: 3, borderRadius: 2, background: i <= step ? '#ff5f33' : 'rgba(255,255,255,0.08)', transition: 'background 0.2s' }} />
          ))}
        </div>
      )}

      <div style={{ padding: '1rem' }}>

        {/* Éxito */}
        {submitted && (
          <div>
            <div style={{ background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.25)', borderRadius: 14, padding: '1.5rem', textAlign: 'center', marginBottom: '1rem' }}>
              <p style={{ margin: '0 0 0.25rem', fontSize: '1.5rem' }}>✓</p>
              <p style={{ margin: '0 0 0.25rem', fontWeight: 900, fontSize: '0.95rem', color: '#10b981' }}>Recepción registrada</p>
              <p style={{ margin: 0, fontSize: '0.65rem', color: '#606075' }}>La orden quedó en estado <strong>Firma Pendiente</strong></p>
            </div>
            <div style={{ background: '#13131a', borderRadius: 12, padding: '1rem', marginBottom: '0.75rem', border: '1px solid rgba(255,255,255,0.05)' }}>
              <p style={{ margin: '0 0 4px', fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Placa</p>
              <p style={{ margin: 0, fontWeight: 900, fontSize: '1.2rem', color: '#ff8c5a' }}>{plate}</p>
            </div>
            <button onClick={reset} style={{ width: '100%', padding: '0.9rem', background: '#ff5f33', border: 'none', borderRadius: 12, color: '#fff', fontWeight: 800, fontSize: '0.9rem', cursor: 'pointer' }}>
              Nueva Recepción
            </button>
          </div>
        )}

        {/* Paso 0: Placa */}
        {!submitted && step === 0 && (
          <>
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, display: 'block', marginBottom: 8 }}>Placa de la motocicleta</label>
              <input
                value={plate}
                onChange={e => setPlate(e.target.value.toUpperCase())}
                onKeyDown={e => e.key === 'Enter' && lookupVehicle()}
                placeholder="ABC123"
                maxLength={6}
                style={{ width: '100%', background: '#13131a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, padding: '1rem', color: '#fff', fontSize: '1.5rem', fontWeight: 900, letterSpacing: '0.12em', textAlign: 'center', outline: 'none', boxSizing: 'border-box' }}
              />
            </div>
            {lookupError && (
              <div style={{ padding: '0.7rem 0.9rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10, marginBottom: '0.75rem' }}>
                <p style={{ margin: 0, fontSize: '0.72rem', color: '#ef4444', fontWeight: 700 }}>{lookupError}</p>
              </div>
            )}
            <button
              onClick={lookupVehicle}
              disabled={looking || !plate.trim()}
              style={{ width: '100%', padding: '0.9rem', background: '#ff5f33', border: 'none', borderRadius: 12, color: '#fff', fontWeight: 800, fontSize: '0.9rem', cursor: 'pointer', opacity: looking || !plate.trim() ? 0.5 : 1 }}
            >
              {looking ? 'Verificando...' : 'Continuar'}
            </button>
          </>
        )}

        {/* Paso 1: Tipo de servicio */}
        {!submitted && step === 1 && (
          <>
            <p style={{ margin: '0 0 0.75rem', fontWeight: 900, fontSize: '1.1rem', color: '#ff8c5a' }}>{plate}</p>
            <p style={{ margin: '0 0 0.6rem', fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>Tipo de servicio</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', marginBottom: '1rem' }}>
              {SERVICE_TYPES.map(t => (
                <button
                  key={t.value}
                  onClick={() => setServiceType(t.value)}
                  style={{ padding: '0.8rem 1rem', borderRadius: 12, border: `1px solid ${serviceType === t.value ? '#ff5f33' : 'rgba(255,255,255,0.08)'}`, background: serviceType === t.value ? 'rgba(255,95,51,0.1)' : 'transparent', color: serviceType === t.value ? '#ff5f33' : '#9ca3af', fontWeight: 700, fontSize: '0.82rem', cursor: 'pointer', textAlign: 'left' }}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <button onClick={() => setStep(2)} style={{ width: '100%', padding: '0.9rem', background: '#ff5f33', border: 'none', borderRadius: 12, color: '#fff', fontWeight: 800, fontSize: '0.9rem', cursor: 'pointer' }}>
              Continuar
            </button>
          </>
        )}

        {/* Paso 2: Datos de recepción */}
        {!submitted && step === 2 && (
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1rem' }}>
              <div>
                <label style={{ fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, display: 'block', marginBottom: 6 }}>Kilometraje actual *</label>
                <input
                  type="number"
                  value={km}
                  onChange={e => setKm(e.target.value)}
                  placeholder="Ej: 12500"
                  inputMode="numeric"
                  style={{ width: '100%', background: '#13131a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10, padding: '0.75rem 0.9rem', color: '#fff', fontSize: '1rem', fontWeight: 700, outline: 'none', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, display: 'block', marginBottom: 6 }}>Nivel de gasolina *</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                  {GAS_LEVELS.map(g => (
                    <button key={g} onClick={() => setGas(g)}
                      style={{ padding: '0.45rem 0.85rem', borderRadius: 20, border: `1px solid ${gas === g ? '#ff5f33' : 'rgba(255,255,255,0.1)'}`, background: gas === g ? 'rgba(255,95,51,0.1)' : 'transparent', color: gas === g ? '#ff5f33' : '#9ca3af', fontWeight: 700, fontSize: '0.72rem', cursor: 'pointer' }}>
                      {g}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label style={{ fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, display: 'block', marginBottom: 6 }}>Motivo de ingreso</label>
                <textarea
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  placeholder="Qué trae la moto, qué reporta el cliente..."
                  rows={3}
                  style={{ width: '100%', background: '#13131a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10, padding: '0.75rem 0.9rem', color: '#fff', fontSize: '0.82rem', resize: 'none', outline: 'none', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, display: 'block', marginBottom: 6 }}>Accesorios (separados por coma)</label>
                <input
                  value={accessories}
                  onChange={e => setAccessories(e.target.value)}
                  placeholder="Casco, chaleco, candado..."
                  style={{ width: '100%', background: '#13131a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10, padding: '0.75rem 0.9rem', color: '#fff', fontSize: '0.82rem', outline: 'none', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, display: 'block', marginBottom: 6 }}>Observaciones generales</label>
                <textarea
                  value={observations}
                  onChange={e => setObservations(e.target.value)}
                  placeholder="Estado general, rayones, acuerdos..."
                  rows={2}
                  style={{ width: '100%', background: '#13131a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10, padding: '0.75rem 0.9rem', color: '#fff', fontSize: '0.82rem', resize: 'none', outline: 'none', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            <button
              onClick={() => setStep(3)}
              disabled={!km || !gas}
              style={{ width: '100%', padding: '0.9rem', background: '#ff5f33', border: 'none', borderRadius: 12, color: '#fff', fontWeight: 800, fontSize: '0.9rem', cursor: 'pointer', opacity: !km || !gas ? 0.5 : 1 }}
            >
              Revisar y Confirmar
            </button>
          </>
        )}

        {/* Paso 3: Confirmar */}
        {!submitted && step === 3 && (
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', marginBottom: '1rem' }}>
              {[
                ['Placa', plate],
                ['Modelo', vehicle?.model || '—'],
                ['Tipo de servicio', SERVICE_TYPES.find(t => t.value === serviceType)?.label],
                ['Kilometraje', `${Number(km).toLocaleString()} km`],
                ['Gasolina', gas],
                ['Motivo', notes || '—'],
                ['Accesorios', accessories || 'Ninguno'],
              ].map(([l, v]) => (
                <div key={l} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', padding: '0.6rem 0.9rem', background: '#13131a', borderRadius: 10, border: '1px solid rgba(255,255,255,0.05)' }}>
                  <span style={{ fontSize: '0.62rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 700, flexShrink: 0, marginRight: '0.5rem' }}>{l}</span>
                  <span style={{ fontSize: '0.72rem', color: '#e2e2f0', fontWeight: 600, textAlign: 'right' }}>{v}</span>
                </div>
              ))}
            </div>

            {submitError && (
              <div style={{ padding: '0.7rem 0.9rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10, marginBottom: '0.75rem' }}>
                <p style={{ margin: 0, fontSize: '0.72rem', color: '#ef4444', fontWeight: 700 }}>{submitError}</p>
              </div>
            )}

            <button
              onClick={submit}
              disabled={submitting}
              style={{ width: '100%', padding: '0.9rem', background: '#ff5f33', border: 'none', borderRadius: 12, color: '#fff', fontWeight: 800, fontSize: '0.9rem', cursor: 'pointer', opacity: submitting ? 0.5 : 1 }}
            >
              {submitting ? 'Registrando...' : 'Confirmar Recepción'}
            </button>
          </>
        )}
      </div>

      <TgNav userRole={user?.role} />
    </div>
  );
}
