'use client';
import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { authFetch } from '../../../lib/authFetch';
import TgNav from '../../../components/tg/TgNav';
import VoiceInput from '../../../components/tg/VoiceInput';
import CameraInput from '../../../components/tg/CameraInput';

// ─── Constantes ──────────────────────────────────────────────────────────────

const STEP = {
  PLATE:        'PLATE',
  NEW_VEHICLE:  'NEW_VEHICLE',
  KM:           'KM',
  GAS:          'GAS',
  NOTES:        'NOTES',
  ACCESSORIES:  'ACCESSORIES',
  OBSERVATIONS: 'OBSERVATIONS',
  CONFIRM:      'CONFIRM',
  DONE:         'DONE',
};

const GAS_CHIPS   = ['Vacío', 'Reserva', '1/4', '1/2', '3/4', 'Lleno'];
const SVC_LABELS  = { regular: 'Mecánica General', km_review: 'Revisión KM', warranty: 'Garantía', pdi: 'Alistamiento' };

let _msgId = 0;
const mkBot  = (text, extra = {}) => ({ id: ++_msgId, role: 'bot',  text, ...extra });
const mkUser = (text)              => ({ id: ++_msgId, role: 'user', text });
const mkTyping = ()                => ({ id: ++_msgId, role: 'bot',  text: '', typing: true });

// ─── Componente principal ─────────────────────────────────────────────────────

export default function TgReception() {
  const router = useRouter();

  const [user, setUser]     = useState(null);
  const [step, setStep]     = useState(STEP.PLATE);
  const [messages, setMsgs] = useState([]);
  const [input, setInput]   = useState('');
  const [busy, setBusy]     = useState(false);   // bloquea input mientras bot "procesa"

  // Datos recolectados
  const [vehicle,      setVehicle]      = useState(null);
  const [isNew,        setIsNew]        = useState(false);
  const [newVeh,       setNewVeh]       = useState({ brand: 'UM', model: '', year: '', color: '', vin: '' });
  const [formData,     setFormData]     = useState({ km: '', gas: '', notes: '', motivos: [], serviceType: 'regular', accessories: [], observations: '' });
  const [ocrDoc,       setOcrDoc]       = useState(null);  // datos extraídos de tarjeta de propiedad

  const bottomRef  = useRef(null);
  const inputRef   = useRef(null);

  // ── Scroll automático ──────────────────────────────────────────────────────
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  // ── Auth ───────────────────────────────────────────────────────────────────
  useEffect(() => {
    const stored = sessionStorage.getItem('um_user');
    const token  = sessionStorage.getItem('um_token');
    if (!stored || !token) { router.replace('/tg'); return; }
    const u = JSON.parse(stored);
    setUser(u);
    pushBot(`Hola${u?.name ? ` ${u.name.split(' ')[0]}` : ''}! ¿Cuál es la placa de la moto?\nPodés escribirla, dictarla 🎙️ o fotografiar la tarjeta 🪪`);
  }, []);

  // ── Helpers de mensajes ────────────────────────────────────────────────────
  const pushBot = useCallback((text, extra) => {
    setMsgs(m => [...m, mkBot(text, extra)]);
  }, []);

  const pushUser = useCallback((text) => {
    setMsgs(m => [...m, mkUser(text)]);
  }, []);

  const showTyping = useCallback(() => {
    const msg = mkTyping();
    setMsgs(m => [...m, msg]);
    return msg.id;
  }, []);

  const removeTyping = useCallback((id) => {
    setMsgs(m => m.filter(x => x.id !== id));
  }, []);

  // ── Flujo principal ────────────────────────────────────────────────────────

  const lookupPlate = useCallback(async (rawPlate) => {
    const plate = rawPlate.trim().toUpperCase().replace(/\s/g, '');
    if (!plate) return;
    pushUser(plate);
    setBusy(true);
    const tid = showTyping();
    try {
      const res = await authFetch(`/orders/mini-app/vehicle/${plate}`);
      removeTyping(tid);
      if (res.status === 401) { router.replace('/tg'); return; }
      if (res.status === 404) {
        setIsNew(true);
        // Si hay datos OCR del documento, pre-llenar
        if (ocrDoc) setNewVeh({ brand: ocrDoc.marca || 'UM', model: ocrDoc.linea || '', year: ocrDoc.modelo || '', color: ocrDoc.color || '', vin: ocrDoc.vin || '' });
        pushBot(`La placa *${plate}* no está registrada. Completá los datos para registrarla:`);
        setFormData(f => ({ ...f, plate }));
        setVehicle({ plate });
        setStep(STEP.NEW_VEHICLE);
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        pushBot(`No pude buscar esa placa: ${err.detail || `Error ${res.status}`}. Intentá de nuevo.`);
        return;
      }
      const data = await res.json();
      if (data.active_order) {
        pushBot(`La moto *${plate}* ya tiene una orden activa en taller. No se puede abrir otra.`);
        return;
      }
      setVehicle(data);
      setFormData(f => ({ ...f, plate }));
      pushBot(`Encontré la moto:\n*${plate}* — ${data.brand || ''} ${data.model || ''} ${data.year || ''}\n\n¿Cuántos kilómetros tiene? Podés escribirlos, dictarlos 🎙️ o foto del tablero 🔢`);
      setStep(STEP.KM);
    } catch (e) {
      removeTyping(tid);
      pushBot(`Error de conexión: ${e.message}. Intentá de nuevo.`);
    } finally {
      setBusy(false);
    }
  }, [ocrDoc, pushBot, pushUser, showTyping, removeTyping, router]);

  const registerNewVehicle = useCallback(async () => {
    if (!newVeh.model.trim()) { pushBot('Necesito al menos el modelo para registrarla.'); return; }
    const tenantId = user?.tenant_id;
    if (!tenantId) { pushBot('Tu usuario no tiene taller asignado. Contactá al admin.'); return; }
    setBusy(true);
    const tid = showTyping();
    try {
      const body = {
        plate: vehicle.plate,
        brand: newVeh.brand || 'UM',
        model: newVeh.model.trim(),
        year:  newVeh.year  ? parseInt(newVeh.year)  : null,
        color: newVeh.color || null,
        vin:   newVeh.vin   || null,
        tenant_id: tenantId,
      };
      const res = await authFetch('/vehicles/', { method: 'POST', body: JSON.stringify(body) });
      removeTyping(tid);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        pushBot(`No pude registrar el vehículo: ${err.detail || `Error ${res.status}`}`);
        return;
      }
      const data = await res.json();
      setVehicle(data);
      pushUser(`Registrado: ${data.brand} ${data.model}`);
      pushBot(`Listo, *${data.plate}* registrada ✓\n\n¿Cuántos kilómetros tiene? Podés escribirlos, dictarlos 🎙️ o foto del tablero 🔢`);
      setStep(STEP.KM);
    } catch (e) {
      removeTyping(tid);
      pushBot(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }, [newVeh, vehicle, user, pushBot, pushUser, showTyping, removeTyping]);

  const submitKm = useCallback((raw) => {
    const km = raw.replace(/[^\d.]/g, '');
    if (!km) { pushBot('No entendí el kilometraje. Escribí solo el número, por ejemplo: 12500'); return; }
    pushUser(raw);
    setFormData(f => ({ ...f, km }));
    pushBot('¿Cuánta gasolina tiene la moto?');
    setStep(STEP.GAS);
  }, [pushBot, pushUser]);

  const submitGas = useCallback((gas) => {
    pushUser(gas);
    setFormData(f => ({ ...f, gas }));
    pushBot('¿Cuál es el motivo de la visita? Describí lo que trae la moto. Podés dictarlo 🎙️');
    setStep(STEP.NOTES);
  }, [pushBot, pushUser]);

  const submitNotes = useCallback(async (raw) => {
    if (!raw.trim()) return;
    pushUser(raw);
    setBusy(true);
    const tid = showTyping();
    try {
      const res = await authFetch('/mini-app/ai/extract-motive', {
        method: 'POST',
        body: JSON.stringify({ text: raw }),
      });
      removeTyping(tid);
      const data = res.ok ? await res.json() : { motivos: [raw], service_type: 'regular' };
      setFormData(f => ({ ...f, notes: raw, motivos: data.motivos, serviceType: data.service_type }));
      pushBot(`Entendido ✓\n\n¿Dejó accesorios con la moto? (casco, candado, etc.). Dictalo 🎙️ o escribilo. Si no hay, tocá *Ninguno*.`);
      setStep(STEP.ACCESSORIES);
    } catch {
      removeTyping(tid);
      setFormData(f => ({ ...f, notes: raw, motivos: [raw], serviceType: 'regular' }));
      pushBot('¿Dejó accesorios con la moto? Si no hay, tocá *Ninguno*.');
      setStep(STEP.ACCESSORIES);
    } finally {
      setBusy(false);
    }
  }, [pushBot, pushUser, showTyping, removeTyping]);

  const submitAccessories = useCallback(async (raw) => {
    pushUser(raw || 'Ninguno');
    if (!raw.trim() || raw.toLowerCase() === 'ninguno') {
      setFormData(f => ({ ...f, accessories: [] }));
      pushBot('¿Alguna observación general? Estado de la moto, rayones, acuerdos... Si no hay, tocá *Saltar*.');
      setStep(STEP.OBSERVATIONS);
      return;
    }
    setBusy(true);
    const tid = showTyping();
    try {
      const res = await authFetch('/mini-app/ai/extract-accessories', {
        method: 'POST',
        body: JSON.stringify({ text: raw }),
      });
      removeTyping(tid);
      const data = res.ok ? await res.json() : { accessories: [raw] };
      setFormData(f => ({ ...f, accessories: data.accessories || [raw] }));
    } catch {
      removeTyping(tid);
      setFormData(f => ({ ...f, accessories: [raw] }));
    } finally {
      setBusy(false);
    }
    pushBot('¿Alguna observación general? Si no hay, tocá *Saltar*.');
    setStep(STEP.OBSERVATIONS);
  }, [pushBot, pushUser, showTyping, removeTyping]);

  const submitObservations = useCallback((raw) => {
    const obs = raw.trim();
    pushUser(obs || 'Sin observaciones');
    setFormData(f => ({ ...f, observations: obs }));
    setStep(STEP.CONFIRM);
    // Bot message se muestra en render del paso CONFIRM
  }, [pushUser]);

  const createOrder = useCallback(async () => {
    setBusy(true);
    const tid = showTyping();
    try {
      const tenantId = vehicle?.tenant_id || user?.tenant_id;
      if (!tenantId) { removeTyping(tid); pushBot('No se pudo determinar el taller. Contactá al admin.'); setBusy(false); return; }
      const body = {
        tenant_id:    tenantId,
        vehicle_id:   vehicle.id,
        client_id:    vehicle.client_id || null,
        service_type: formData.serviceType,
        reception: {
          mileage_km:           parseFloat(formData.km),
          gas_level:            formData.gas,
          customer_notes:       formData.notes || null,
          accessories:          formData.accessories,
          general_observations: formData.observations || null,
          damage_photos_urls:   [],
          intake_answers:       [],
          warranty_warnings:    null,
        },
      };
      const res = await authFetch('/orders/', { method: 'POST', body: JSON.stringify(body) });
      removeTyping(tid);
      if (res.status === 401) { router.replace('/tg'); return; }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        pushBot(`No pude crear la orden: ${err.detail || `Error ${res.status}`}. Intentá de nuevo.`);
        return;
      }
      setStep(STEP.DONE);
    } catch (e) {
      removeTyping(tid);
      pushBot(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }, [vehicle, user, formData, pushBot, showTyping, removeTyping, router]);

  // ── Enviar input de texto ──────────────────────────────────────────────────
  const handleSend = useCallback(() => {
    const val = input.trim();
    if (!val || busy) return;
    setInput('');
    switch (step) {
      case STEP.PLATE:        return lookupPlate(val);
      case STEP.KM:           return submitKm(val);
      case STEP.GAS:          return submitGas(val);
      case STEP.NOTES:        return submitNotes(val);
      case STEP.ACCESSORIES:  return submitAccessories(val);
      case STEP.OBSERVATIONS: return submitObservations(val);
    }
  }, [input, busy, step, lookupPlate, submitKm, submitGas, submitNotes, submitAccessories, submitObservations]);

  // ── Chips de respuesta rápida ──────────────────────────────────────────────
  const handleChip = useCallback((val) => {
    if (busy) return;
    switch (step) {
      case STEP.GAS:          return submitGas(val);
      case STEP.ACCESSORIES:  return submitAccessories('');
      case STEP.OBSERVATIONS: return submitObservations('');
    }
  }, [busy, step, submitGas, submitAccessories, submitObservations]);

  // ── Chips contextuales ─────────────────────────────────────────────────────
  const chips = {
    [STEP.GAS]:          GAS_CHIPS,
    [STEP.ACCESSORIES]:  ['Ninguno'],
    [STEP.OBSERVATIONS]: ['Saltar'],
  }[step] || [];

  // ── Handlers de VoiceInput y CameraInput ──────────────────────────────────
  const onTranscript = useCallback((text) => {
    setInput(text);
    inputRef.current?.focus();
  }, []);

  const onDocumentPhoto = useCallback((data) => {
    setOcrDoc(data);
    if (data.placa) {
      setInput(data.placa);
      if (step === STEP.PLATE) lookupPlate(data.placa);
    }
  }, [step, lookupPlate]);

  const onOdometerPhoto = useCallback((data) => {
    const km  = data.kilometraje?.replace(/[^\d.]/g, '') || '';
    const gas = data.gasolina || '';
    if (km) {
      pushUser(`📷 Tablero: ${km} km${gas ? ` · ${gas}` : ''}`);
      if (gas) {
        // Tenemos ambos datos — avanzar dos pasos
        setFormData(f => ({ ...f, km, gas }));
        pushBot(`Perfecto: *${Number(km).toLocaleString()} km* y gasolina *${gas}* ✓\n\n¿Cuál es el motivo de la visita? Dictalo 🎙️`);
        setStep(STEP.NOTES);
      } else {
        setFormData(f => ({ ...f, km }));
        pushBot(`*${Number(km).toLocaleString()} km* registrado ✓\n\n¿Cuánta gasolina tiene la moto?`);
        setStep(STEP.GAS);
      }
    } else {
      pushBot('No pude leer el kilometraje. Escribilo manualmente.');
    }
  }, [pushBot, pushUser]);

  // ── Render del paso CONFIRM ───────────────────────────────────────────────
  const confirmShown = useRef(false);
  useEffect(() => {
    if (step === STEP.CONFIRM && !confirmShown.current) {
      confirmShown.current = true;
      pushBot('Revisá el resumen antes de confirmar:');
    }
  }, [step, pushBot]);

  // Reset
  const reset = () => {
    _msgId = 0;
    confirmShown.current = false;
    setStep(STEP.PLATE); setMsgs([]); setInput(''); setBusy(false);
    setVehicle(null); setIsNew(false); setOcrDoc(null);
    setNewVeh({ brand: 'UM', model: '', year: '', color: '', vin: '' });
    setFormData({ km: '', gas: '', notes: '', motivos: [], serviceType: 'regular', accessories: [], observations: '' });
    const u = user;
    setTimeout(() => pushBot(`Hola${u?.name ? ` ${u.name.split(' ')[0]}` : ''}! ¿Cuál es la placa de la moto?\nPodés escribirla, dictarla 🎙️ o fotografiar la tarjeta 🪪`), 50);
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh', background: '#0a0a0c' }}>

      {/* Header */}
      <div style={{ background: '#13131a', borderBottom: '1px solid rgba(255,255,255,0.06)', padding: '0.8rem 1.1rem', flexShrink: 0, display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
        <button onClick={() => router.back()} style={{ background: 'none', border: 'none', color: '#606075', cursor: 'pointer', fontSize: '1.1rem', padding: 0, lineHeight: 1 }}>←</button>
        <div>
          <p style={{ margin: 0, fontWeight: 900, fontSize: '0.85rem', color: '#fff' }}>Nueva Recepción</p>
          <p style={{ margin: 0, fontSize: '0.58rem', color: '#606075' }}>
            {step === STEP.DONE ? 'Completado' : `${vehicle?.plate || 'Sonia — Mini App'}`}
          </p>
        </div>
      </div>

      {/* Mensajes */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0.9rem 0.75rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>

        {messages.map(msg => (
          <div key={msg.id} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
            {msg.typing ? (
              <div style={bubbleStyle('bot')}>
                <span style={{ display: 'inline-flex', gap: 4 }}>
                  {[0,1,2].map(i => <span key={i} style={{ width: 6, height: 6, borderRadius: '50%', background: '#606075', display: 'inline-block', animation: `tgDot 1.2s ${i*0.2}s ease-in-out infinite` }} />)}
                </span>
              </div>
            ) : (
              <div style={bubbleStyle(msg.role)}>
                {formatText(msg.text)}
              </div>
            )}
          </div>
        ))}

        {/* Tarjeta de vehículo nuevo */}
        {step === STEP.NEW_VEHICLE && (
          <div style={{ background: '#13131a', border: '1px solid rgba(245,158,11,0.25)', borderRadius: 14, padding: '1rem', margin: '0.25rem 0' }}>
            <p style={{ margin: '0 0 0.75rem', fontSize: '0.6rem', color: '#f59e0b', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Datos del vehículo nuevo</p>
            {[
              { label: 'Marca',  key: 'brand', placeholder: 'UM' },
              { label: 'Modelo *', key: 'model', placeholder: 'Renegade 200, NKD 125…' },
              { label: 'Año',    key: 'year',  placeholder: '2023', type: 'number' },
              { label: 'Color',  key: 'color', placeholder: 'Rojo, Negro…' },
              { label: 'VIN',    key: 'vin',   placeholder: 'Opcional (17 caracteres)' },
            ].map(f => (
              <div key={f.key} style={{ marginBottom: '0.5rem' }}>
                <label style={{ fontSize: '0.52rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, display: 'block', marginBottom: 4 }}>{f.label}</label>
                <input
                  type={f.type || 'text'}
                  value={newVeh[f.key]}
                  onChange={e => setNewVeh(v => ({ ...v, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  style={{ width: '100%', background: '#0a0a0c', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '0.6rem 0.75rem', color: '#fff', fontSize: '0.8rem', outline: 'none', boxSizing: 'border-box' }}
                />
              </div>
            ))}
            <button onClick={registerNewVehicle} disabled={busy || !newVeh.model.trim()}
              style={{ width: '100%', padding: '0.75rem', background: '#ff5f33', border: 'none', borderRadius: 10, color: '#fff', fontWeight: 800, fontSize: '0.82rem', cursor: 'pointer', opacity: busy || !newVeh.model.trim() ? 0.5 : 1, marginTop: '0.25rem' }}>
              {busy ? 'Registrando…' : 'Registrar y continuar →'}
            </button>
          </div>
        )}

        {/* Selector de tipo de servicio en CONFIRM */}
        {step === STEP.CONFIRM && (
          <div style={{ background: '#13131a', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 14, padding: '1rem' }}>
            <p style={{ margin: '0 0 0.6rem', fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>Resumen de Recepción</p>
            {[
              ['Placa',    formData.plate || vehicle?.plate],
              ['Vehículo', vehicle ? `${vehicle.brand || ''} ${vehicle.model || ''}`.trim() || '—' : '—'],
              ['KM',       `${Number(formData.km || 0).toLocaleString()} km`],
              ['Gasolina', formData.gas],
              ['Motivo',   formData.motivos?.join(', ') || formData.notes || '—'],
              ['Accesorios', formData.accessories?.length ? formData.accessories.join(', ') : 'Ninguno'],
              ['Observaciones', formData.observations || 'Ninguna'],
            ].map(([l, v]) => (
              <div key={l} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.45rem 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <span style={{ fontSize: '0.6rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 700 }}>{l}</span>
                <span style={{ fontSize: '0.72rem', color: '#e2e2f0', fontWeight: 600, textAlign: 'right', maxWidth: '60%' }}>{v}</span>
              </div>
            ))}
            {/* Tipo de servicio editable */}
            <p style={{ margin: '0.75rem 0 0.4rem', fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
              Tipo de servicio{formData.motivos?.length ? ' (detectado por IA)' : ''}
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem', marginBottom: '0.75rem' }}>
              {Object.entries(SVC_LABELS).map(([v, l]) => (
                <button key={v} onClick={() => setFormData(f => ({ ...f, serviceType: v }))}
                  style={{ padding: '0.35rem 0.75rem', borderRadius: 20, border: `1px solid ${formData.serviceType === v ? '#ff5f33' : 'rgba(255,255,255,0.1)'}`, background: formData.serviceType === v ? 'rgba(255,95,51,0.12)' : 'transparent', color: formData.serviceType === v ? '#ff5f33' : '#9ca3af', fontWeight: 700, fontSize: '0.68rem', cursor: 'pointer' }}>
                  {l}
                </button>
              ))}
            </div>
            <button onClick={createOrder} disabled={busy}
              style={{ width: '100%', padding: '0.85rem', background: '#ff5f33', border: 'none', borderRadius: 11, color: '#fff', fontWeight: 800, fontSize: '0.88rem', cursor: 'pointer', opacity: busy ? 0.5 : 1 }}>
              {busy ? 'Registrando…' : 'Confirmar Recepción ✓'}
            </button>
          </div>
        )}

        {/* Pantalla de éxito */}
        {step === STEP.DONE && (
          <div style={{ background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)', borderRadius: 14, padding: '1.5rem', textAlign: 'center', margin: '0.5rem 0' }}>
            <p style={{ margin: '0 0 0.3rem', fontSize: '1.8rem' }}>✅</p>
            <p style={{ margin: '0 0 0.2rem', fontWeight: 900, fontSize: '1rem', color: '#10b981' }}>Recepción registrada</p>
            <p style={{ margin: '0 0 1rem', fontSize: '0.65rem', color: '#606075' }}>La orden quedó en estado <strong style={{ color: '#f59e0b' }}>Firma Pendiente</strong></p>
            <p style={{ margin: '0 0 0.25rem', fontWeight: 900, fontSize: '1.3rem', color: '#ff8c5a', letterSpacing: '0.08em' }}>
              {formData.plate || vehicle?.plate}
            </p>
            {vehicle?.model && (
              <p style={{ margin: '0 0 1.25rem', fontSize: '0.7rem', color: '#606075' }}>{vehicle.brand} {vehicle.model} {vehicle.year || ''}</p>
            )}
            <button onClick={reset} style={{ width: '100%', padding: '0.85rem', background: '#ff5f33', border: 'none', borderRadius: 11, color: '#fff', fontWeight: 800, fontSize: '0.88rem', cursor: 'pointer' }}>
              Nueva Recepción
            </button>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Chips de respuesta rápida */}
      {chips.length > 0 && step !== STEP.DONE && (
        <div style={{ display: 'flex', gap: '0.4rem', padding: '0.4rem 0.75rem 0.25rem', overflowX: 'auto', flexShrink: 0, scrollbarWidth: 'none' }}>
          {chips.map(c => (
            <button key={c} onClick={() => handleChip(c)} disabled={busy}
              style={{ padding: '0.35rem 0.85rem', borderRadius: 20, border: '1px solid rgba(255,95,51,0.35)', background: 'rgba(255,95,51,0.08)', color: '#ff8c5a', fontWeight: 700, fontSize: '0.72rem', cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0 }}>
              {c}
            </button>
          ))}
        </div>
      )}

      {/* Barra de input */}
      {![STEP.NEW_VEHICLE, STEP.CONFIRM, STEP.DONE].includes(step) && (
        <div style={{ background: '#13131a', borderTop: '1px solid rgba(255,255,255,0.06)', padding: '0.6rem 0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem', flexShrink: 0 }}>

          {/* Cámara contextual */}
          {step === STEP.PLATE && (
            <CameraInput mode="document" onResult={onDocumentPhoto} onError={msg => pushBot(msg)} disabled={busy} size={40} />
          )}
          {step === STEP.KM && (
            <CameraInput mode="odometer" onResult={onOdometerPhoto} onError={msg => pushBot(msg)} disabled={busy} size={40} />
          )}

          {/* Input de texto */}
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
            disabled={busy}
            placeholder={placeholders[step] || 'Escribí tu respuesta…'}
            style={{ flex: 1, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 22, padding: '0.6rem 0.9rem', color: '#fff', fontSize: '0.85rem', outline: 'none', minWidth: 0 }}
          />

          {/* Voz */}
          <VoiceInput onTranscript={onTranscript} onError={msg => pushBot(msg)} disabled={busy} size={40} />

          {/* Enviar */}
          <button onClick={handleSend} disabled={busy || !input.trim()}
            style={{ width: 40, height: 40, borderRadius: '50%', border: 'none', background: input.trim() && !busy ? '#ff5f33' : 'rgba(255,255,255,0.06)', color: '#fff', fontSize: '1rem', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, transition: 'background 0.15s' }}>
            ↑
          </button>
        </div>
      )}

      <TgNav userRole={user?.role} />

      <style>{`
        @keyframes tgDot {
          0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
          40%            { transform: scale(1);   opacity: 1; }
        }
      `}</style>
    </div>
  );
}

// ─── Helpers de estilo ────────────────────────────────────────────────────────

function bubbleStyle(role) {
  const isBot = role === 'bot';
  return {
    maxWidth: '82%',
    padding: '0.6rem 0.85rem',
    borderRadius: isBot ? '4px 18px 18px 18px' : '18px 4px 18px 18px',
    background: isBot ? '#1e1e2a' : 'rgba(255,95,51,0.18)',
    border: `1px solid ${isBot ? 'rgba(255,255,255,0.06)' : 'rgba(255,95,51,0.25)'}`,
    fontSize: '0.82rem',
    lineHeight: 1.45,
    color: isBot ? '#d1d1e0' : '#fff',
    wordBreak: 'break-word',
  };
}

function formatText(text) {
  if (!text) return null;
  return text.split('\n').map((line, i) => {
    const parts = line.split(/(\*[^*]+\*)/g).map((p, j) =>
      p.startsWith('*') && p.endsWith('*')
        ? <strong key={j} style={{ color: '#fff', fontWeight: 800 }}>{p.slice(1, -1)}</strong>
        : p
    );
    return <span key={i}>{parts}{i < text.split('\n').length - 1 ? <br /> : null}</span>;
  });
}

const placeholders = {
  [STEP.PLATE]:        'Ej: ABC123',
  [STEP.KM]:           'Ej: 12500',
  [STEP.GAS]:          'O elegí un nivel arriba ↑',
  [STEP.NOTES]:        '¿Qué trae la moto?',
  [STEP.ACCESSORIES]:  'Casco, candado…',
  [STEP.OBSERVATIONS]: 'Rayones, acuerdos…',
};
