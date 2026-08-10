'use client';
import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { authFetch } from '../../../lib/authFetch';
import { needsTenantSelection, getActiveTenantId } from '../../../lib/activeTenant';
import TgNav from '../../../components/tg/TgNav';
import VoiceInput from '../../../components/tg/VoiceInput';
import CameraInput from '../../../components/tg/CameraInput';

// ─── Constantes ───────────────────────────────────────────────────────────────
const STEP = {
  PLATE:             'PLATE',
  CONFIRMING_PLATE_FORMAT: 'CONFIRMING_PLATE_FORMAT',
  CONFIRMING_OCR:    'CONFIRMING_OCR',
  CORRECTING_OCR:    'CORRECTING_OCR',
  CONFIRMING_CLIENT: 'CONFIRMING_CLIENT',
  CONFIRMING_RETURNING_CLIENT: 'CONFIRMING_RETURNING_CLIENT',
  SELECTING_CLIENT_FIELD:      'SELECTING_CLIENT_FIELD',
  EDITING_CLIENT_FIELD:        'EDITING_CLIENT_FIELD',
  ASKING_PHONE:      'ASKING_PHONE',
  ASKING_CEDULA:     'ASKING_CEDULA',
  NEW_VEHICLE_FORM:  'NEW_VEHICLE_FORM',
  KM:                'KM',
  GAS:               'GAS',
  ASKING_PHOTOS:     'ASKING_PHOTOS',
  ASKING_PHOTO_DESC: 'ASKING_PHOTO_DESC',
  ACCESSORIES:       'ACCESSORIES',
  NOTES:             'NOTES',
  CONFIRMING_MOTIVE: 'CONFIRMING_MOTIVE',
  ASKING_SVC_TYPE:   'ASKING_SVC_TYPE',
  INTAKE:            'INTAKE',
  OBSERVATIONS:      'OBSERVATIONS',
  CONFIRM:           'CONFIRM',
  DONE:              'DONE',
};

// Placas colombianas: 3 letras + 2 números + 1 letra, sin espacios (ej:
// ABC12D). Aplicado sobre `plate` YA normalizada (trim/upper/sin espacios).
// No bloquea -- algunas placas legítimas (diplomáticas, oficiales, motos muy
// antiguas) no siguen este patrón; solo pide confirmación explícita.
const PLATE_FORMAT_RE = /^[A-Z]{3}\d{2}[A-Z]$/;

const GAS_CHIPS   = ['Vacío', 'Reserva', '1/4', '1/2', '3/4', 'Lleno'];
const SVC_LABELS  = { regular: 'Mecánica General', km_review: 'Revisión KM', warranty: 'Garantía', pdi: 'Alistamiento' };
const CANCEL_WORDS = ['cancelar','cancela','cancelo','anular','anula','abortar','no quiero','salir','parar','basta','terminar','stop'];
const INTAKE_QUESTIONS = {
  warranty:  [
    '¿Tipo de terreno por donde habitualmente conduce?',
    '¿Conduce habitualmente con acompañante?',
    '¿Estimado de peso aproximado del conductor?',
    '¿Cuál es la velocidad promedio a la que conduce?',
    '¿El lugar de parqueo es abierto o cerrado?',
    '¿El vehículo ha sido intervenido en un centro de servicio distinto a un autorizado?',
  ],
  km_review: [
    '¿Tipo de terreno por donde habitualmente conduce?',
    '¿Conduce habitualmente con acompañante?',
    '¿Estimado de peso aproximado del conductor?',
    '¿Su vehículo funciona correctamente?',
  ],
  regular: ['¿Tipo de terreno por donde habitualmente conduce?'],
  quick:   ['¿Tipo de terreno por donde habitualmente conduce?', '¿Su vehículo funciona correctamente?'],
};
const STORAGE_KEY = 'reception_draft';

// Campos editables del cliente vinculado a la moto (orden del teclado de selección).
// Mirrors telegram-bot/bot/handlers/reception.py's CLIENT_FIELDS verbatim -- the
// Mini App is a copy of Sonia's canonical confirm/edit flow, not the reverse.
const CLIENT_FIELDS = [
  ['name',    'Nombre'],
  ['phone',   'Teléfono'],
  ['email',   'Email'],
  ['address', 'Dirección'],
];
const CLIENT_FIELD_LABELS = Object.fromEntries(CLIENT_FIELDS);

function buildClientSummary(client) {
  let lines = '👤 *Datos del cliente registrado:*\n';
  CLIENT_FIELDS.forEach(([key, label]) => {
    const value = client?.[key];
    lines += `• *${label}:* ${value || 'N/D'}\n`;
  });
  return lines;
}

const fieldLabelStyle = { fontSize: '0.52rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, display: 'block', marginBottom: 4 };
const fieldInputStyle = { width: '100%', background: '#0a0a0c', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '0.6rem 0.75rem', color: '#fff', fontSize: '0.8rem', outline: 'none', boxSizing: 'border-box' };
const vinHintStyle    = { margin: '0.3rem 0 0', fontSize: '0.62rem', color: '#606075' };
// Explicit background/color on every <option> -- without it, the dropdown
// popup inherits light text on the browser's default light background and
// is invisible until hovered.
const optionStyle = { background: '#1a1a22', color: '#fff' };

let _msgId = 0;
const mkBot    = (text, extra = {}) => ({ id: ++_msgId, role: 'bot',  text, ...extra });
const mkUser   = (text)              => ({ id: ++_msgId, role: 'user', text });
const mkTyping = ()                  => ({ id: ++_msgId, role: 'bot',  text: '', typing: true });

const b64ToBlob = (b64, mime = 'image/jpeg') => {
  const data  = b64.includes(',') ? b64.split(',')[1] : b64;
  const bytes = atob(data);
  const arr   = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  return new Blob([arr], { type: mime });
};

// ─── Componente ───────────────────────────────────────────────────────────────
export default function TgReception() {
  const router = useRouter();

  const [user,     setUser]    = useState(null);
  const [step,     setStep]    = useState(STEP.PLATE);
  const [messages, setMsgs]    = useState([]);
  const [input,    setInput]   = useState('');
  const [busy,     setBusy]    = useState(false);
  const [cancelPending, setCancelPending] = useState(false);

  // Datos recolectados — NADA se persiste en DB hasta el paso final
  const [ocrData,     setOcrData]     = useState(null);
  // Placa que no matcheó `PLATE_FORMAT_RE`, en espera de confirmación
  // explícita (STEP.CONFIRMING_PLATE_FORMAT) antes de consultarla al
  // backend -- guarda también el `docData` del OCR (si venía de ahí) para
  // no perderlo al retomar el flujo tras la confirmación.
  const [pendingPlateCheck, setPendingPlateCheck] = useState(null);
  const [vehicleId,   setVehicleId]   = useState(null);
  const [vehicleData, setVehicleData] = useState(null);
  const [isNew,       setIsNew]       = useState(false);
  const [newVeh,      setNewVeh]      = useState({ brand: 'UM', model: '', year: '', color: '', vin: '' });
  const [clientPhone, setClientPhone] = useState('');
  const [clientIdentification, setClientIdentification] = useState('');
  const [clientEdits, setClientEdits] = useState({});
  const [editingClientField, setEditingClientField] = useState(null);
  const [formData,    setFormData]    = useState({
    plate: '', km: '', gas: '', notes: '', motivos: [], serviceType: 'regular',
    accessories: [], observations: '', intakeAnswers: [], pdfUrl: null,
  });
  const [evidenceItems, setEvidenceItems] = useState([]);
  const [pendingPhoto,  setPendingPhoto]  = useState(null);
  const [intakeQuestions, setIntakeQuestions] = useState([]);
  const [intakeIdx,       setIntakeIdx]       = useState(0);
  const [vehicleModels,   setVehicleModels]   = useState([]); // catálogo estandarizado (GET /vehicle-models)
  const [vinLookupStatus, setVinLookupStatus] = useState('idle'); // idle | loading | found | not_found

  const bottomRef   = useRef(null);
  const inputRef    = useRef(null);
  const photoRef    = useRef(null);
  const confirmShown = useRef(false);

  // ── Scroll ────────────────────────────────────────────────────────────────
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  // ── Auto-save draft ───────────────────────────────────────────────────────
  useEffect(() => {
    if (step === STEP.DONE) { sessionStorage.removeItem(STORAGE_KEY); return; }
    if (step === STEP.PLATE) return;
    const draft = {
      step, ocrData, vehicleId, isNew, newVeh, clientPhone, clientIdentification, formData,
      clientEdits, editingClientField, pendingPlateCheck,
      vehicleData: vehicleData
        ? { plate: vehicleData.plate, brand: vehicleData.brand, model: vehicleData.model, year: vehicleData.year, id: vehicleData.id, client_id: vehicleData.client_id }
        : null,
      evidenceItems: evidenceItems.map(e => ({ type: e.type, desc: e.desc })),
      intakeQuestions, intakeIdx,
      msgs: messages.slice(-80).map(m => ({ id: m.id, role: m.role, text: m.text })),
    };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
  }, [step, messages]);

  // ── Auth + restore draft ──────────────────────────────────────────────────
  useEffect(() => {
    const stored = sessionStorage.getItem('um_user');
    const token  = sessionStorage.getItem('um_token');
    if (!stored || !token) { router.replace('/tg'); return; }
    const u = JSON.parse(stored);
    if (needsTenantSelection(u)) { router.replace('/tg/tenant'); return; }
    setUser(u);

    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) {
      try {
        const d = JSON.parse(raw);
        if (d.step && ![STEP.DONE, STEP.PLATE].includes(d.step)) {
          _msgId = Math.max(...(d.msgs || []).map(m => m.id || 0), 0);
          setStep(d.step);
          setMsgs([...(d.msgs || []), mkBot('↩️ Retomamos donde quedamos.')]);
          setOcrData(d.ocrData || null);
          setPendingPlateCheck(d.pendingPlateCheck || null);
          setVehicleId(d.vehicleId || null);
          setVehicleData(d.vehicleData || null);
          setIsNew(d.isNew || false);
          setNewVeh(d.newVeh || { brand: 'UM', model: '', year: '', color: '', vin: '' });
          setClientPhone(d.clientPhone || '');
          setClientIdentification(d.clientIdentification || '');
          setClientEdits(d.clientEdits || {});
          setEditingClientField(d.editingClientField || null);
          setFormData(d.formData || { plate: '', km: '', gas: '', notes: '', motivos: [], serviceType: 'regular', accessories: [], observations: '', intakeAnswers: [], pdfUrl: null });
          setEvidenceItems(d.evidenceItems || []);
          setIntakeQuestions(d.intakeQuestions || []);
          setIntakeIdx(d.intakeIdx || 0);
          return;
        }
      } catch {}
    }

    _msgId = 0;
    setMsgs([mkBot(`Hola${u?.name ? ` ${u.name.split(' ')[0]}` : ''}! ¿Cuál es la placa de la moto?\nPodés escribirla, dictarla 🎙️ o fotografiar la tarjeta de propiedad 🪪`)]);
  }, []);

  // ── Catálogo de modelos (para el select del vehículo nuevo) ─────────────────
  useEffect(() => {
    authFetch('/vehicle-models')
      .then(res => (res.ok ? res.json() : []))
      .then(data => setVehicleModels(Array.isArray(data) ? data : []))
      .catch(() => setVehicleModels([]));
  }, []);

  // ── VIN → maestro de VINs ────────────────────────────────────────────────
  // Fetch+parse compartido. Cuando el VIN resuelve en el maestro, ese dato de
  // base de datos REEMPLAZA lo que haya en el formulario (tipeado a mano o
  // leído por OCR de la tarjeta de propiedad) -- mismo criterio "el maestro
  // de VINs siempre gana cuando está presente" ya usado por
  // `distribuidor/entrega` y `historical-orders` (`data.field || f.field`).
  // Decisión de producto explícita (2026-08-06): "el sistema lee el numero
  // de chasis o vin, lo busca los datos en la base de datos y eso son los
  // datos del vehiculo" -- el texto leído por OCR es inherentemente
  // impreciso (calidad de foto, letra manuscrita) y nunca debe pisar el dato
  // oficial del maestro.
  const fetchVinMasterData = useCallback(async (rawVin) => {
    const vin = (rawVin || '').trim().toUpperCase();
    if (vin.length !== 17) return null;
    try {
      const res = await authFetch(`/vehicles/vin/${encodeURIComponent(vin)}`);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }, []);

  const lookupVin = useCallback(async (rawVin) => {
    const vin = rawVin.trim().toUpperCase();
    if (vin.length !== 17) { setVinLookupStatus('idle'); return; }
    setVinLookupStatus('loading');
    const data = await fetchVinMasterData(vin);
    if (!data) { setVinLookupStatus('not_found'); return; }
    setNewVeh(v => ({
      ...v,
      model: data.model || v.model,
      year:  data.year ? String(data.year) : v.year,
      color: data.color || v.color,
    }));
    setVinLookupStatus('found');
  }, [fetchVinMasterData]);

  // ── Helpers de mensajes ───────────────────────────────────────────────────
  const pushBot  = useCallback((text, extra) => setMsgs(m => [...m, mkBot(text, extra)]), []);
  const pushUser = useCallback((text) => setMsgs(m => [...m, mkUser(text)]), []);
  const showTyping   = useCallback(() => { const msg = mkTyping(); setMsgs(m => [...m, msg]); return msg.id; }, []);
  const removeTyping = useCallback((id) => setMsgs(m => m.filter(x => x.id !== id)), []);

  // ── Cancelar ──────────────────────────────────────────────────────────────
  const doReset = useCallback((u) => {
    sessionStorage.removeItem(STORAGE_KEY);
    _msgId = 0; confirmShown.current = false;
    setStep(STEP.PLATE); setMsgs([]); setInput(''); setBusy(false); setCancelPending(false);
    setOcrData(null); setPendingPlateCheck(null); setVehicleId(null); setVehicleData(null); setIsNew(false);
    setNewVeh({ brand: 'UM', model: '', year: '', color: '', vin: '' });
    setVinLookupStatus('idle');
    setClientPhone(''); setClientIdentification(''); setClientEdits({}); setEditingClientField(null);
    setEvidenceItems([]); setPendingPhoto(null);
    setIntakeQuestions([]); setIntakeIdx(0);
    setFormData({ plate: '', km: '', gas: '', notes: '', motivos: [], serviceType: 'regular', accessories: [], observations: '', intakeAnswers: [], pdfUrl: null });
    const usr = u;
    setTimeout(() => setMsgs([mkBot(`Listo, cancelado. ¿Cuál es la placa?\nPodés escribirla, dictarla 🎙️ o fotografiar la tarjeta 🪪`)]), 50);
  }, []);

  const requestCancel = useCallback(() => {
    setCancelPending(true);
    setMsgs(m => [...m, mkBot('¿Seguro que querés cancelar? Se perderán todos los datos.')]);
  }, []);

  // ── PLATE ─────────────────────────────────────────────────────────────────
  // Backend lookup + response handling, separado del chequeo de formato de
  // arriba para que tanto la placa bien formada (camino directo) como la
  // "sí, es correcta" tras STEP.CONFIRMING_PLATE_FORMAT (override explícito)
  // compartan la MISMA lógica, sin duplicar el authFetch/404/active_order.
  const performPlateLookup = useCallback(async (plate, docData = null) => {
    setBusy(true);
    const tid = showTyping();
    try {
      const res = await authFetch(`/orders/mini-app/vehicle/${plate}`);
      removeTyping(tid);
      if (res.status === 401) { router.replace('/tg'); return; }
      setFormData(f => ({ ...f, plate }));

      if (res.status === 404) {
        setIsNew(true); setVehicleId(null); setVehicleData({ plate });
        if (docData) {
          // El VIN leído por OCR sí se confía como identificador -- pero
          // marca/modelo/año/color NO: si ese VIN resuelve en el maestro,
          // el dato de base de datos reemplaza por completo el texto leído
          // de la foto. Solo si el VIN no resuelve (unidad todavía no
          // importada, u OCR no capturó VIN) se usa el texto del OCR como
          // respaldo, editable a mano en el formulario.
          const vinMaster = await fetchVinMasterData(docData.vin);
          if (vinMaster) {
            setVinLookupStatus('found');
            setNewVeh({
              brand: vinMaster.brand || docData.marca || 'UM',
              model: vinMaster.model || '',
              year:  vinMaster.year ? String(vinMaster.year) : '',
              color: vinMaster.color || '',
              vin:   docData.vin || '',
            });
          } else {
            setNewVeh({ brand: docData.marca || 'UM', model: docData.linea || '', year: docData.modelo || '', color: docData.color || '', vin: docData.vin || '' });
          }
        }
        pushBot(`La placa *${plate}* no está registrada. Es una moto nueva.\n¿Cuál es el *teléfono del cliente*? Dictalo 🎙️ o escribilo.`);
        setStep(STEP.ASKING_PHONE);
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        pushBot(`No pude buscar esa placa: ${err.detail || `Error ${res.status}`}. Intentá de nuevo.`);
        return;
      }
      const data = await res.json();
      if (data.active_order) {
        const holder = data.active_order.tenant_name || 'otro taller';
        const city   = data.active_order.tenant_city ? ` (${data.active_order.tenant_city})` : '';
        pushBot(`La moto *${plate}* ya tiene una orden activa en ${holder}${city}. No se puede abrir otra.`);
        return;
      }
      setIsNew(false); setVehicleId(data.id); setVehicleData(data);
      const vLabel = [data.brand, data.model, data.year].filter(Boolean).join(' ');
      if (data.client) {
        // Moto con cliente vinculado -- mostramos sus datos y pedimos confirmación,
        // mirroring the bot's handle_ocr_confirmation known-vehicle branch (ADR21).
        setClientEdits({});
        pushBot(`¡Esta moto ya ha estado en el taller!\n*${plate}* — ${vLabel || '—'}\n\n${buildClientSummary(data.client)}\n¿Siguen correctos estos datos?`);
        setStep(STEP.CONFIRMING_RETURNING_CLIENT);
      } else {
        // Sin cliente vinculado aún -- comportamiento histórico, sin cambios (ADR16).
        pushBot(`¡Esta moto ya ha estado en el taller!\n*${plate}* — ${vLabel || '—'}\n\n¿Ingresamos al taller?`);
        setStep(STEP.CONFIRMING_CLIENT);
      }
    } catch (e) {
      removeTyping(tid);
      pushBot(`Error de conexión: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }, [pushBot, showTyping, removeTyping, router, fetchVinMasterData]);

  // Chequea el formato de placa colombiano ANTES de consultar el backend --
  // si no matchea, defiere la consulta hasta que el personal confirme
  // explícitamente (STEP.CONFIRMING_PLATE_FORMAT), sin tocar `busy`/typing
  // (todavía no se disparó ninguna llamada de red).
  const lookupPlate = useCallback((rawPlate, docData = null) => {
    const plate = rawPlate.trim().toUpperCase().replace(/\s/g, '');
    if (!plate) return;

    if (!PLATE_FORMAT_RE.test(plate)) {
      setPendingPlateCheck({ plate, docData });
      pushBot(`La placa *${plate}* no tiene el formato esperado (3 letras + 2 números + 1 letra, ej: ABC12D). ¿Es correcta?`);
      setStep(STEP.CONFIRMING_PLATE_FORMAT);
      return;
    }

    performPlateLookup(plate, docData);
  }, [pushBot, performPlateLookup]);

  const confirmPlateFormat = useCallback(() => {
    pushUser('Confirmar ✓');
    const check = pendingPlateCheck;
    setPendingPlateCheck(null);
    if (check?.plate) performPlateLookup(check.plate, check.docData);
  }, [pushUser, pendingPlateCheck, performPlateLookup]);

  const correctPlateFormat = useCallback(() => {
    pushUser('Corregir ✏️');
    pushBot('Escribí o dictá la placa correcta:');
    setStep(pendingPlateCheck?.docData ? STEP.CORRECTING_OCR : STEP.PLATE);
    setPendingPlateCheck(null);
  }, [pushUser, pushBot, pendingPlateCheck]);

  // ── OCR documento ─────────────────────────────────────────────────────────
  const onDocumentPhoto = useCallback((data) => {
    setOcrData(data);
    if (!data.placa) { pushBot('No pude leer la placa. Escribila manualmente.'); return; }
    const lines = [`📷 Tarjeta de propiedad:`];
    lines.push(`Placa: *${data.placa}*`);
    if (data.marca || data.linea) lines.push(`${[data.marca, data.linea].filter(Boolean).join(' ')}`);
    if (data.modelo)     lines.push(`Año: ${data.modelo}`);
    if (data.color)      lines.push(`Color: ${data.color}`);
    if (data.vin)        lines.push(`VIN: ${data.vin}`);
    if (data.propietario) lines.push(`Propietario: ${data.propietario}`);
    setMsgs(m => [...m, mkUser(lines.join('\n'))]);
    pushBot('Datos extraídos de la tarjeta. ¿Son correctos?');
    setStep(STEP.CONFIRMING_OCR);
  }, [pushBot]);

  // ── CONFIRMING_OCR ────────────────────────────────────────────────────────
  const confirmOcr = useCallback(() => {
    pushUser('Confirmar ✓');
    lookupPlate(ocrData.placa, ocrData);
  }, [ocrData, pushUser, lookupPlate]);

  const correctOcr = useCallback(() => {
    pushUser('Corregir ✏️');
    pushBot('Escribí o dictá la placa correcta:');
    setStep(STEP.CORRECTING_OCR);
  }, [pushUser, pushBot]);

  // ── CONFIRMING_CLIENT ─────────────────────────────────────────────────────
  const confirmClient = useCallback(() => {
    pushUser('Ingresar al taller →');
    setEvidenceItems([]);
    pushBot(`¿Cuántos kilómetros tiene la moto?\nEscribí, dictá 🎙️ o foto del tablero 📷`);
    setStep(STEP.KM);
  }, [pushUser, pushBot]);

  // ── CONFIRMING_RETURNING_CLIENT / SELECTING_CLIENT_FIELD / EDITING_CLIENT_FIELD ─
  // Mirrors the bot's handle_returning_client_confirmation / handle_client_field_selection /
  // handle_client_field_value (PR6, telegram-bot/bot/handlers/reception.py) field-for-field:
  // confirm-as-is is a pure no-op, edits are captured one field at a time and batched
  // into a SINGLE PATCH /vehicles/{plate}/client call on "Listo", and a PATCH failure
  // is surfaced but never blocks the rest of reception.
  const confirmReturningClient = useCallback(() => {
    pushUser('Sí, siguen correctos');
    setEvidenceItems([]);
    pushBot(`¿Cuántos kilómetros tiene la moto?\nEscribí, dictá 🎙️ o foto del tablero 📷`);
    setStep(STEP.KM);
  }, [pushUser, pushBot]);

  const openClientFieldEdit = useCallback(() => {
    pushUser('No, corregir algo');
    pushBot('Dale, decime qué dato(s) del cliente querés corregir:');
    setStep(STEP.SELECTING_CLIENT_FIELD);
  }, [pushUser, pushBot]);

  const selectClientField = useCallback((label) => {
    const entry = CLIENT_FIELDS.find(([, l]) => l === label);
    if (!entry) return;
    const [key] = entry;
    pushUser(label);
    setEditingClientField(key);
    pushBot(`¿Cuál es el nuevo *${label.toLowerCase()}* del cliente? Escribilo o dictalo 🎙️`);
    setStep(STEP.EDITING_CLIENT_FIELD);
  }, [pushUser, pushBot]);

  const submitClientFieldValue = useCallback((raw) => {
    const value = raw.trim();
    const key = editingClientField;
    const label = CLIENT_FIELD_LABELS[key] || 'dato';
    if (!value) { pushBot(`No logré identificar el nuevo valor de *${label.toLowerCase()}*. ¿Me lo repetís?`); return; }
    pushUser(value);
    setClientEdits(e => ({ ...e, [key]: value }));
    setEditingClientField(null);
    pushBot(`${label} actualizado a *${value}*. ✅\n\n¿Corregís algo más?`);
    setStep(STEP.SELECTING_CLIENT_FIELD);
  }, [editingClientField, pushUser, pushBot]);

  const finishClientEdits = useCallback(async () => {
    pushUser('✅ Listo');
    const plate = formData.plate;
    const edits = clientEdits;
    if (Object.keys(edits).length > 0 && plate) {
      setBusy(true);
      try {
        const res = await authFetch(`/vehicles/${plate}/client`, { method: 'PATCH', body: JSON.stringify(edits) });
        if (!res.ok) {
          pushBot('⚠️ No pude guardar los cambios del cliente, pero seguimos con la recepción.');
        }
      } catch {
        pushBot('⚠️ No pude guardar los cambios del cliente, pero seguimos con la recepción.');
      } finally {
        setBusy(false);
      }
    }
    setEvidenceItems([]);
    pushBot(`¿Cuántos kilómetros tiene la moto?\nEscribí, dictá 🎙️ o foto del tablero 📷`);
    setStep(STEP.KM);
  }, [formData.plate, clientEdits, pushUser, pushBot]);

  // ── ASKING_PHONE ──────────────────────────────────────────────────────────
  const goToVehicleForm = useCallback(() => {
    const hasOcr = ocrData && (ocrData.linea || ocrData.marca);
    pushBot(hasOcr
      ? 'Revisá y completá los datos del vehículo (el modelo es obligatorio):'
      : 'Completá los datos del vehículo nuevo (el modelo es obligatorio):');
    setStep(STEP.NEW_VEHICLE_FORM);
  }, [pushBot, ocrData]);

  const handlePhone = useCallback((val) => {
    const phone = val.trim().replace(/\s/g, '');
    if (!phone) { pushBot('Necesito el teléfono del cliente para continuar.'); return; }
    pushUser(phone);
    setClientPhone(phone);
    // La cédula ya vino de la tarjeta de propiedad leída por OCR -- no hace
    // falta pedirla de nuevo. Si no, se pide a mano (única forma hoy de
    // identificar a un cliente que ya existe con otra moto).
    if (ocrData?.numero_documento_propietario) {
      setClientIdentification(ocrData.numero_documento_propietario);
      goToVehicleForm();
      return;
    }
    pushBot('¿Cuál es la *cédula del cliente*? Dictala 🎙️ o escribila.');
    setStep(STEP.ASKING_CEDULA);
  }, [pushUser, pushBot, ocrData, goToVehicleForm]);

  // ── ASKING_CEDULA ─────────────────────────────────────────────────────────
  const handleCedula = useCallback((val) => {
    const cedula = val.trim().replace(/\s/g, '');
    if (!cedula) { pushBot('Necesito la cédula del cliente para continuar.'); return; }
    pushUser(cedula);
    setClientIdentification(cedula);
    goToVehicleForm();
  }, [pushUser, pushBot, goToVehicleForm]);

  // ── NEW_VEHICLE_FORM — vehículo NO se crea aquí, se crea al final ─────────
  const confirmNewVehicle = useCallback(() => {
    if (!newVeh.model.trim()) { pushBot('El modelo es obligatorio.'); return; }
    pushUser(`${newVeh.brand} ${newVeh.model}${newVeh.year ? ` ${newVeh.year}` : ''}`);
    pushBot(`Datos guardados ✓\n¿Cuántos kilómetros tiene la moto?\nEscribí, dictá 🎙️ o foto del tablero 📷`);
    setEvidenceItems([]);
    setStep(STEP.KM);
  }, [newVeh, pushUser, pushBot]);

  // ── KM ────────────────────────────────────────────────────────────────────
  const submitKm = useCallback((raw) => {
    const km = raw.replace(/[^\d.]/g, '');
    if (!km) { pushBot('No entendí el KM. Escribí solo el número, ej: 12500'); return; }
    pushUser(raw);
    setFormData(f => ({ ...f, km }));
    pushBot('¿Cuánta gasolina tiene la moto?');
    setStep(STEP.GAS);
  }, [pushBot, pushUser]);

  const onOdometerPhoto = useCallback((data) => {
    const km  = data.kilometraje?.replace(/[^\d.]/g, '') || '';
    const gas = data.gasolina || '';
    if (!km) { pushBot('No pude leer el KM. Escribilo manualmente.'); return; }
    pushUser(`📷 Tablero: ${km} km${gas ? ` · ${gas}` : ''}`);
    setFormData(f => ({ ...f, km, ...(gas ? { gas } : {}) }));
    if (gas) {
      pushBot(`*${Number(km).toLocaleString()} km* y gasolina *${gas}* ✓\n\n¿Tiene fotos de daños o evidencias para adjuntar?`);
      setStep(STEP.ASKING_PHOTOS);
    } else {
      pushBot(`*${Number(km).toLocaleString()} km* ✓\n\n¿Cuánta gasolina tiene?`);
      setStep(STEP.GAS);
    }
  }, [pushBot, pushUser]);

  // ── GAS ───────────────────────────────────────────────────────────────────
  const submitGas = useCallback((gas) => {
    pushUser(gas);
    setFormData(f => ({ ...f, gas }));
    pushBot('¿Tiene fotos de daños, rayones u otras evidencias para adjuntar?');
    setStep(STEP.ASKING_PHOTOS);
  }, [pushBot, pushUser]);

  // ── ASKING_PHOTOS ─────────────────────────────────────────────────────────
  const handleEvidenceFile = useCallback((e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setPendingPhoto(ev.target.result);
      pushBot('¿Qué muestra esta foto? Describila brevemente o dictá 🎙️');
      setStep(STEP.ASKING_PHOTO_DESC);
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  }, [pushBot]);

  const addTextOnly = useCallback(() => {
    pushUser('📝 Solo observación');
    setPendingPhoto(null);
    pushBot('Describí la observación:');
    setStep(STEP.ASKING_PHOTO_DESC);
  }, [pushUser, pushBot]);

  const skipPhotos = useCallback(() => {
    pushUser(evidenceItems.length > 0 ? 'Continuar' : 'Sin fotos');
    pushBot('¿Dejó accesorios con la moto? (casco, candado, alforjas…) Dictalo 🎙️ o escribilo.');
    setStep(STEP.ACCESSORIES);
  }, [pushUser, pushBot, evidenceItems.length]);

  // ── ASKING_PHOTO_DESC ─────────────────────────────────────────────────────
  const submitPhotoDesc = useCallback((desc) => {
    const item = pendingPhoto
      ? { type: 'photo', base64: pendingPhoto, desc: desc || '' }
      : { type: 'text',  base64: null,         desc };
    if (!desc && !pendingPhoto) return;
    pushUser(pendingPhoto ? `📷 ${desc || 'Sin descripción'}` : `📝 ${desc}`);
    setEvidenceItems(items => {
      const next = [...items, item];
      pushBot(`Evidencia ${next.length} guardada ✓\n¿Agregás otra foto, una observación o continuamos?`);
      return next;
    });
    setPendingPhoto(null);
    setStep(STEP.ASKING_PHOTOS);
  }, [pendingPhoto, pushUser, pushBot]);

  const skipPhotoDesc = useCallback(() => {
    if (pendingPhoto) {
      setEvidenceItems(items => {
        const next = [...items, { type: 'photo', base64: pendingPhoto, desc: '' }];
        pushBot(`Evidencia ${next.length} guardada ✓\n¿Agregás otra foto, una observación o continuamos?`);
        return next;
      });
      pushUser('📷 Sin descripción');
    }
    setPendingPhoto(null);
    setStep(STEP.ASKING_PHOTOS);
  }, [pendingPhoto, pushUser, pushBot]);

  // ── ACCESSORIES ───────────────────────────────────────────────────────────
  const submitAccessories = useCallback(async (raw) => {
    pushUser(raw || 'Ninguno');
    if (!raw.trim() || raw.toLowerCase() === 'ninguno') {
      setFormData(f => ({ ...f, accessories: [] }));
      pushBot('¿Cuál es el *motivo de la visita*? Describí lo que trae la moto. Podés dictarlo 🎙️');
      setStep(STEP.NOTES);
      return;
    }
    setBusy(true);
    const tid = showTyping();
    try {
      const res = await authFetch('/mini-app/ai/extract-accessories', { method: 'POST', body: JSON.stringify({ text: raw }) });
      removeTyping(tid);
      const data = res.ok ? await res.json() : { accessories: [raw] };
      setFormData(f => ({ ...f, accessories: data.accessories || [raw] }));
    } catch {
      removeTyping(tid);
      setFormData(f => ({ ...f, accessories: [raw] }));
    } finally { setBusy(false); }
    pushBot('¿Cuál es el *motivo de la visita*? Describí lo que trae la moto. Podés dictarlo 🎙️');
    setStep(STEP.NOTES);
  }, [pushBot, pushUser, showTyping, removeTyping]);

  // ── NOTES ─────────────────────────────────────────────────────────────────
  const submitNotes = useCallback(async (raw) => {
    if (!raw.trim()) return;
    pushUser(raw);
    setBusy(true);
    const tid = showTyping();
    try {
      const res = await authFetch('/mini-app/ai/extract-motive', { method: 'POST', body: JSON.stringify({ text: raw }) });
      removeTyping(tid);
      const data = res.ok ? await res.json() : { motivos: [raw], service_type: 'regular' };
      const motivos = data.motivos || [raw];
      const svcType = data.service_type || 'regular';
      setFormData(f => ({ ...f, notes: raw, motivos, serviceType: svcType }));
      const list = motivos.map(m => `• ${m}`).join('\n');
      pushBot(`Motivos identificados:\n${list}\n\nTipo detectado: *${SVC_LABELS[svcType] || svcType}*\n\n¿Es correcto?`);
      setStep(STEP.CONFIRMING_MOTIVE);
    } catch {
      removeTyping(tid);
      setFormData(f => ({ ...f, notes: raw, motivos: [raw], serviceType: 'regular' }));
      pushBot(`Motivo: *${raw}*\nTipo: *Mecánica General*\n\n¿Es correcto?`);
      setStep(STEP.CONFIRMING_MOTIVE);
    } finally { setBusy(false); }
  }, [pushBot, pushUser, showTyping, removeTyping]);

  // ── CONFIRMING_MOTIVE ─────────────────────────────────────────────────────
  const confirmMotive = useCallback(() => {
    pushUser('Confirmar ✓');
    const questions = INTAKE_QUESTIONS[formData.serviceType] || [];
    if (questions.length > 0) {
      setIntakeQuestions(questions); setIntakeIdx(0);
      setFormData(f => ({ ...f, intakeAnswers: [] }));
      pushBot(`Pregunta 1/${questions.length}:\n${questions[0]}`);
      setStep(STEP.INTAKE);
    } else {
      pushBot('¿Alguna observación general? Estado, rayones, acuerdos con el cliente... Si no hay, tocá *Saltar*.');
      setStep(STEP.OBSERVATIONS);
    }
  }, [pushUser, pushBot, formData.serviceType]);

  const changeSvcType = useCallback(() => {
    pushUser('Cambiar tipo de servicio');
    pushBot('Elegí el tipo de servicio:');
    setStep(STEP.ASKING_SVC_TYPE);
  }, [pushUser, pushBot]);

  const correctMotive = useCallback(() => {
    pushUser('Corregir motivo');
    pushBot('Volvé a describir el motivo de la visita:');
    setStep(STEP.NOTES);
  }, [pushUser, pushBot]);

  // ── ASKING_SVC_TYPE ───────────────────────────────────────────────────────
  const selectSvcType = useCallback((type) => {
    pushUser(SVC_LABELS[type]);
    setFormData(f => {
      const motivos = f.motivos || [];
      const list = motivos.map(m => `• ${m}`).join('\n') || f.notes || '—';
      pushBot(`Tipo: *${SVC_LABELS[type]}*\n\nMotivos:\n${list}\n\n¿Confirmamos?`);
      return { ...f, serviceType: type };
    });
    setStep(STEP.CONFIRMING_MOTIVE);
  }, [pushUser, pushBot]);

  // ── INTAKE ────────────────────────────────────────────────────────────────
  const submitIntake = useCallback((raw) => {
    if (!raw.trim()) return;
    pushUser(raw);
    const newAnswers = [...(formData.intakeAnswers || []), { pregunta: intakeQuestions[intakeIdx], respuesta: raw }];
    setFormData(f => ({ ...f, intakeAnswers: newAnswers }));
    const next = intakeIdx + 1;
    setIntakeIdx(next);
    if (next < intakeQuestions.length) {
      pushBot(`Pregunta ${next + 1}/${intakeQuestions.length}:\n${intakeQuestions[next]}`);
    } else {
      pushBot('¿Alguna observación general? Estado, rayones, acuerdos con el cliente... Si no hay, tocá *Saltar*.');
      setStep(STEP.OBSERVATIONS);
    }
  }, [pushUser, pushBot, formData.intakeAnswers, intakeQuestions, intakeIdx]);

  // ── OBSERVATIONS ──────────────────────────────────────────────────────────
  const submitObservations = useCallback((raw) => {
    const obs = raw.trim();
    pushUser(obs || 'Sin observaciones');
    setFormData(f => ({ ...f, observations: obs }));
    setStep(STEP.CONFIRM);
  }, [pushUser]);

  useEffect(() => {
    if (step === STEP.CONFIRM && !confirmShown.current) {
      confirmShown.current = true;
      pushBot('Revisá el resumen antes de confirmar:');
    }
  }, [step, pushBot]);

  // ── createOrder — único punto donde se escribe en DB ─────────────────────
  const createOrder = useCallback(async () => {
    setBusy(true);
    const tid = showTyping();
    try {
      const tenantId = getActiveTenantId(user);
      if (!tenantId) { removeTyping(tid); pushBot('No se pudo determinar el taller.'); setBusy(false); return; }

      let vid = vehicleId;
      let cid = vehicleData?.client_id || null;

      // 1. Moto nueva: crear cliente + vehículo
      if (isNew) {
        try {
          const cr = await authFetch('/users/', { method: 'POST', body: JSON.stringify({
            name: ocrData?.propietario || 'Desconocido',
            role: 'client', tenant_id: tenantId,
            phone: clientPhone || null,
            identification: clientIdentification || ocrData?.numero_documento_propietario || null,
          })});
          if (cr.ok || cr.status === 409) {
            cid = (await cr.json().catch(() => ({}))).id || null;
          } else {
            pushBot('⚠️ No pude registrar el cliente, pero seguimos con la recepción.');
          }
        } catch {
          pushBot('⚠️ No pude registrar el cliente, pero seguimos con la recepción.');
        }

        const vr = await authFetch('/vehicles/', { method: 'POST', body: JSON.stringify({
          plate: formData.plate, brand: newVeh.brand || 'UM', model: newVeh.model.trim(),
          year: newVeh.year ? parseInt(newVeh.year) : null,
          color: newVeh.color || null, vin: newVeh.vin || null, tenant_id: tenantId,
        })});
        if (!vr.ok) {
          const err = await vr.json().catch(() => ({}));
          removeTyping(tid); pushBot(`No pude registrar el vehículo: ${err.detail || `Error ${vr.status}`}`);
          setBusy(false); return;
        }
        const vd = await vr.json();
        vid = vd.id;
        setVehicleId(vid); setVehicleData({ ...vd, client_id: cid });
      }

      // 2. Crear orden
      const payload = {
        tenant_id:     tenantId,
        vehicle_id:    vid,
        client_id:     cid,
        client_phone:  clientPhone || null,
        technician_id: user?.id || null,
        service_type:  formData.serviceType,
        reception: {
          mileage_km:           parseFloat(formData.km) || 0,
          gas_level:            formData.gas,
          customer_notes:       (formData.motivos || []).map(m => `- ${m}`).join('\n') || formData.notes || null,
          accessories:          formData.accessories || [],
          general_observations: formData.observations || null,
          damage_photos_urls:   [],
          intake_answers:       formData.intakeAnswers || [],
          warranty_warnings:    null,
        },
      };

      const or = await authFetch('/orders/', { method: 'POST', body: JSON.stringify(payload) });
      removeTyping(tid);
      if (or.status === 401) { router.replace('/tg'); return; }
      if (!or.ok) {
        const err = await or.json().catch(() => ({}));
        const nestedDetail = err.detail && typeof err.detail === 'object' ? err.detail.detail : null;
        const message = nestedDetail || (typeof err.detail === 'string' ? err.detail : `Error ${or.status}`);
        pushBot(`No pude crear la orden: ${message}`);
        setBusy(false); return;
      }
      const orderData = await or.json();
      const orderId   = orderData.id;
      const pdfUrl    = orderData?.reception?.reception_pdf_url || null;
      setFormData(f => ({ ...f, pdfUrl }));

      // 3. Subir fotos de evidencia
      const photos = evidenceItems.filter(e => e.type === 'photo' && e.base64);
      const texts  = evidenceItems.filter(e => e.type === 'text');
      if (photos.length > 0 || texts.length > 0) {
        try {
          const fd = new FormData();
          photos.forEach((item, i) => fd.append('files', b64ToBlob(item.base64), `evidence_${i}.jpg`));
          fd.append('descriptions', JSON.stringify(photos.map(e => e.desc)));
          if (texts.length > 0) fd.append('text_observations', JSON.stringify(texts.map(e => e.desc)));
          await authFetch(`/orders/${orderId}/photos`, { method: 'POST', body: fd });
        } catch {}
      }

      sessionStorage.removeItem(STORAGE_KEY);
      setStep(STEP.DONE);
    } catch (e) {
      removeTyping(tid);
      pushBot(`Error: ${e.message}`);
      setBusy(false);
    } finally { setBusy(false); }
  }, [vehicleId, vehicleData, user, isNew, newVeh, ocrData, clientPhone, clientIdentification, formData, evidenceItems, pushBot, showTyping, removeTyping, router]);

  // ── handleSendValue ───────────────────────────────────────────────────────
  const handleSendValue = useCallback((val) => {
    if (!val?.trim() || busy) return;
    const v = val.trim();

    if (cancelPending) {
      if (['sí','si','yes','cancelar','confirmar'].some(w => v.toLowerCase().startsWith(w))) {
        doReset(user);
      } else {
        setCancelPending(false);
        pushBot('Ok, continuamos.');
      }
      return;
    }

    if (!cancelPending && step !== STEP.DONE) {
      const lower = v.toLowerCase();
      if (CANCEL_WORDS.some(w => lower === w || lower.startsWith(w + ' ') || lower.endsWith(' ' + w))) {
        requestCancel(); return;
      }
    }

    switch (step) {
      case STEP.PLATE: {
        const plate = v.toUpperCase().replace(/\s/g, '');
        pushUser(plate);
        lookupPlate(plate);
        return;
      }
      case STEP.CORRECTING_OCR: {
        const plate = v.toUpperCase().replace(/\s/g, '');
        pushUser(plate);
        lookupPlate(plate, ocrData);
        return;
      }
      case STEP.ASKING_PHONE:      return handlePhone(v);
      case STEP.ASKING_CEDULA:     return handleCedula(v);
      case STEP.EDITING_CLIENT_FIELD: return submitClientFieldValue(v);
      case STEP.KM:                return submitKm(v);
      case STEP.ASKING_PHOTO_DESC: return submitPhotoDesc(v);
      case STEP.ACCESSORIES:       return submitAccessories(v);
      case STEP.NOTES:             return submitNotes(v);
      case STEP.INTAKE:            return submitIntake(v);
      case STEP.OBSERVATIONS:      return submitObservations(v);
    }
  }, [busy, step, cancelPending, doReset, user, requestCancel, pushBot, pushUser,
      ocrData, lookupPlate, handlePhone, handleCedula, submitClientFieldValue, submitKm,
      submitPhotoDesc, submitAccessories, submitNotes, submitIntake, submitObservations]);

  const handleSend = useCallback(() => {
    const val = input.trim(); if (!val) return;
    setInput(''); handleSendValue(val);
  }, [input, handleSendValue]);

  const onTranscript = useCallback((text) => {
    setInput(text); handleSendValue(text);
  }, [handleSendValue]);

  // ── Chips ─────────────────────────────────────────────────────────────────
  const handleChip = useCallback((val) => {
    if (busy) return;
    if (cancelPending) { handleSendValue(val); return; }
    switch (step) {
      case STEP.CONFIRMING_PLATE_FORMAT:
        return val.startsWith('Confirmar') ? confirmPlateFormat() : correctPlateFormat();
      case STEP.CONFIRMING_OCR:    return val.startsWith('Confirmar') ? confirmOcr() : correctOcr();
      case STEP.CONFIRMING_CLIENT: return confirmClient();
      case STEP.CONFIRMING_RETURNING_CLIENT:
        return val.startsWith('Sí') ? confirmReturningClient() : openClientFieldEdit();
      case STEP.SELECTING_CLIENT_FIELD:
        return val.includes('Listo') ? finishClientEdits() : selectClientField(val);
      case STEP.GAS:               return submitGas(val);
      case STEP.ASKING_PHOTOS:
        if (val.includes('observación')) return addTextOnly();
        return skipPhotos();
      case STEP.ASKING_PHOTO_DESC: return skipPhotoDesc();
      case STEP.ACCESSORIES:       return submitAccessories('');
      case STEP.CONFIRMING_MOTIVE:
        if (val.startsWith('Confirmar')) return confirmMotive();
        if (val.startsWith('Cambiar'))   return changeSvcType();
        return correctMotive();
      case STEP.ASKING_SVC_TYPE:
        return selectSvcType(Object.keys(SVC_LABELS).find(k => SVC_LABELS[k] === val) || 'regular');
      case STEP.OBSERVATIONS: return submitObservations('');
    }
  }, [busy, step, cancelPending, handleSendValue, confirmPlateFormat, correctPlateFormat,
      confirmOcr, correctOcr, confirmClient,
      confirmReturningClient, openClientFieldEdit, finishClientEdits, selectClientField,
      submitGas, addTextOnly, skipPhotos, skipPhotoDesc, submitAccessories,
      confirmMotive, changeSvcType, correctMotive, selectSvcType, submitObservations]);

  const chips = (() => {
    if (cancelPending) return ['Sí, cancelar', 'No, continuar'];
    switch (step) {
      case STEP.CONFIRMING_PLATE_FORMAT: return ['Confirmar ✓', 'Corregir ✏️'];
      case STEP.CONFIRMING_OCR:    return ['Confirmar ✓', 'Corregir ✏️'];
      case STEP.CONFIRMING_CLIENT: return ['Ingresar al taller →'];
      case STEP.CONFIRMING_RETURNING_CLIENT: return ['Sí, siguen correctos', 'No, corregir algo'];
      case STEP.SELECTING_CLIENT_FIELD:      return [...CLIENT_FIELDS.map(([, label]) => label), '✅ Listo'];
      case STEP.GAS:               return GAS_CHIPS;
      case STEP.ASKING_PHOTOS:     return evidenceItems.length > 0
                                     ? ['📝 Solo observación', '✅ Continuar']
                                     : ['📝 Solo observación', '✅ Sin fotos'];
      case STEP.ASKING_PHOTO_DESC: return ['Saltar descripción'];
      case STEP.ACCESSORIES:       return ['Ninguno'];
      case STEP.CONFIRMING_MOTIVE: return ['Confirmar ✓', 'Cambiar tipo', 'Corregir motivo'];
      case STEP.ASKING_SVC_TYPE:   return Object.values(SVC_LABELS);
      case STEP.OBSERVATIONS:      return ['Saltar'];
      default:                     return [];
    }
  })();

  const INPUT_STEPS = [STEP.PLATE, STEP.CORRECTING_OCR, STEP.ASKING_PHONE, STEP.ASKING_CEDULA, STEP.EDITING_CLIENT_FIELD, STEP.KM,
                       STEP.ASKING_PHOTO_DESC, STEP.ACCESSORIES, STEP.NOTES, STEP.INTAKE, STEP.OBSERVATIONS];
  const showInputBar = (INPUT_STEPS.includes(step) || cancelPending) && step !== STEP.DONE;

  // ─── RENDER ────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh', background: '#0a0a0c' }}>

      {/* Header */}
      <div style={{ background: '#13131a', borderBottom: '1px solid rgba(255,255,255,0.06)', padding: '0.8rem 1.1rem', flexShrink: 0, display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
        <img src="/logo.png" alt="UM" style={{ height: 28, width: 'auto', objectFit: 'contain', flexShrink: 0, opacity: 0.9 }} />
        <button onClick={() => router.back()} style={{ background: 'none', border: 'none', color: '#606075', cursor: 'pointer', fontSize: '1.1rem', padding: 0, lineHeight: 1 }}>←</button>
        <div style={{ flex: 1 }}>
          <p style={{ margin: 0, fontWeight: 900, fontSize: '0.85rem', color: '#fff' }}>Nueva Recepción</p>
          <p style={{ margin: 0, fontSize: '0.58rem', color: '#606075' }}>
            {step === STEP.DONE ? 'Completado' : (formData.plate || 'Sonia — Mini App')}
          </p>
        </div>
        {![STEP.DONE, STEP.PLATE].includes(step) && !cancelPending && (
          <button onClick={requestCancel} style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 8, color: '#ef4444', fontSize: '0.68rem', fontWeight: 700, padding: '0.3rem 0.65rem', cursor: 'pointer' }}>
            Cancelar
          </button>
        )}
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
              <div style={bubbleStyle(msg.role)}>{formatText(msg.text)}</div>
            )}
          </div>
        ))}

        {/* Formulario vehículo nuevo */}
        {step === STEP.NEW_VEHICLE_FORM && (
          <div style={{ background: '#13131a', border: '1px solid rgba(245,158,11,0.25)', borderRadius: 14, padding: '1rem', margin: '0.25rem 0' }}>
            <p style={{ margin: '0 0 0.75rem', fontSize: '0.6rem', color: '#f59e0b', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Vehículo nuevo — {formData.plate}</p>

            {/* VIN primero: si está en el maestro, completa marca/modelo/año/color solo. */}
            <div style={{ marginBottom: '0.5rem' }}>
              <label style={fieldLabelStyle}>VIN</label>
              <input type="text" value={newVeh.vin}
                onChange={e => { setNewVeh(v => ({ ...v, vin: e.target.value })); setVinLookupStatus('idle'); }}
                onBlur={e => lookupVin(e.target.value)}
                placeholder="17 caracteres — opcional"
                style={fieldInputStyle} />
              {vinLookupStatus === 'loading'    && <p style={vinHintStyle}>Buscando en el maestro de VINs…</p>}
              {vinLookupStatus === 'found'      && <p style={{ ...vinHintStyle, color: '#22c55e' }}>✓ Datos encontrados y completados abajo.</p>}
              {vinLookupStatus === 'not_found'  && <p style={vinHintStyle}>No está en el maestro — completá manualmente.</p>}
            </div>

            {[
              { label: 'Marca', key: 'brand', placeholder: 'UM' },
            ].map(f => (
              <div key={f.key} style={{ marginBottom: '0.5rem' }}>
                <label style={fieldLabelStyle}>{f.label}</label>
                <input type="text" value={newVeh[f.key]}
                  onChange={e => setNewVeh(v => ({ ...v, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  style={fieldInputStyle} />
              </div>
            ))}

            {/* Modelo: select del catálogo estandarizado; texto libre solo si el catálogo no cargó. */}
            <div style={{ marginBottom: '0.5rem' }}>
              <label style={fieldLabelStyle}>Modelo *</label>
              {vehicleModels.length > 0 ? (
                <select value={newVeh.model} onChange={e => setNewVeh(v => ({ ...v, model: e.target.value }))} style={fieldInputStyle}>
                  <option value="" style={optionStyle}>— Seleccioná un modelo —</option>
                  {vehicleModels.map(m => (
                    <option key={m.id} value={m.modelo} style={optionStyle}>{m.modelo}</option>
                  ))}
                </select>
              ) : (
                <input type="text" value={newVeh.model}
                  onChange={e => setNewVeh(v => ({ ...v, model: e.target.value }))}
                  placeholder="Renegade 200, NKD 125…"
                  style={fieldInputStyle} />
              )}
            </div>

            {[
              { label: 'Año',   key: 'year',  placeholder: '2023', type: 'number' },
              { label: 'Color', key: 'color', placeholder: 'Rojo, Negro…' },
            ].map(f => (
              <div key={f.key} style={{ marginBottom: '0.5rem' }}>
                <label style={fieldLabelStyle}>{f.label}</label>
                <input type={f.type || 'text'} value={newVeh[f.key]}
                  onChange={e => setNewVeh(v => ({ ...v, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  style={fieldInputStyle} />
              </div>
            ))}
            <button onClick={confirmNewVehicle} disabled={busy || !newVeh.model.trim()}
              style={{ width: '100%', padding: '0.75rem', background: '#ff5f33', border: 'none', borderRadius: 10, color: '#fff', fontWeight: 800, fontSize: '0.82rem', cursor: 'pointer', opacity: busy || !newVeh.model.trim() ? 0.5 : 1, marginTop: '0.25rem' }}>
              Continuar →
            </button>
          </div>
        )}

        {/* Confirmación final */}
        {step === STEP.CONFIRM && (
          <div style={{ background: '#13131a', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 14, padding: '1rem' }}>
            <p style={{ margin: '0 0 0.6rem', fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>Resumen de Recepción</p>
            {[
              ['Placa',       formData.plate],
              ['Vehículo',    vehicleData ? `${vehicleData.brand || ''} ${vehicleData.model || ''}`.trim() || '—' : `${newVeh.brand} ${newVeh.model}`.trim() || '—'],
              ['KM',          `${Number(formData.km || 0).toLocaleString()} km`],
              ['Gasolina',    formData.gas || '—'],
              ['Teléfono',    clientPhone || '—'],
              ['Motivo',      (formData.motivos?.join(', ') || formData.notes || '—')],
              ['Servicio',    SVC_LABELS[formData.serviceType] || '—'],
              ['Accesorios',  formData.accessories?.length ? formData.accessories.join(', ') : 'Ninguno'],
              ['Evidencias',  evidenceItems.length > 0 ? `${evidenceItems.length} elemento(s)` : 'Ninguna'],
              ['Observaciones', formData.observations || 'Ninguna'],
            ].map(([l, v]) => (
              <div key={l} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.45rem 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <span style={{ fontSize: '0.6rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 700 }}>{l}</span>
                <span style={{ fontSize: '0.72rem', color: '#e2e2f0', fontWeight: 600, textAlign: 'right', maxWidth: '60%' }}>{v}</span>
              </div>
            ))}
            {formData.intakeAnswers?.length > 0 && (
              <details style={{ marginTop: '0.5rem' }}>
                <summary style={{ fontSize: '0.6rem', color: '#606075', cursor: 'pointer', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Preguntas de intake ({formData.intakeAnswers.length})
                </summary>
                {formData.intakeAnswers.map((a, i) => (
                  <div key={i} style={{ padding: '0.35rem 0', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                    <p style={{ margin: 0, fontSize: '0.58rem', color: '#606075' }}>{a.pregunta}</p>
                    <p style={{ margin: 0, fontSize: '0.68rem', color: '#e2e2f0', fontWeight: 600 }}>{a.respuesta}</p>
                  </div>
                ))}
              </details>
            )}
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

        {/* Éxito */}
        {step === STEP.DONE && (
          <div style={{ background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)', borderRadius: 14, padding: '1.5rem', textAlign: 'center', margin: '0.5rem 0' }}>
            <p style={{ margin: '0 0 0.3rem', fontSize: '1.8rem' }}>✅</p>
            <p style={{ margin: '0 0 0.2rem', fontWeight: 900, fontSize: '1rem', color: '#10b981' }}>Recepción registrada</p>
            <p style={{ margin: '0 0 1rem', fontSize: '0.65rem', color: '#606075' }}>Orden en estado <strong style={{ color: '#f59e0b' }}>Firma Pendiente</strong></p>
            <p style={{ margin: '0 0 0.25rem', fontWeight: 900, fontSize: '1.3rem', color: '#ff8c5a', letterSpacing: '0.08em' }}>{formData.plate}</p>
            {(vehicleData?.model || newVeh.model) && (
              <p style={{ margin: '0 0 1.25rem', fontSize: '0.7rem', color: '#606075' }}>
                {vehicleData?.brand || newVeh.brand} {vehicleData?.model || newVeh.model} {vehicleData?.year || newVeh.year || ''}
              </p>
            )}
            {formData.pdfUrl && (
              <a href={formData.pdfUrl} target="_blank" rel="noreferrer"
                style={{ display: 'block', width: '100%', padding: '0.75rem', background: 'rgba(16,185,129,0.12)', border: '1px solid rgba(16,185,129,0.3)', borderRadius: 10, color: '#10b981', fontWeight: 800, fontSize: '0.85rem', textDecoration: 'none', marginBottom: '0.75rem', boxSizing: 'border-box' }}>
                📄 Ver Hoja de Recepción (PDF)
              </a>
            )}
            <button onClick={() => doReset(user)}
              style={{ width: '100%', padding: '0.85rem', background: '#ff5f33', border: 'none', borderRadius: 11, color: '#fff', fontWeight: 800, fontSize: '0.88rem', cursor: 'pointer' }}>
              Nueva Recepción
            </button>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Botón de cámara para evidencias (solo en ASKING_PHOTOS) */}
      {step === STEP.ASKING_PHOTOS && (
        <div style={{ padding: '0 0.75rem 0.3rem', flexShrink: 0 }}>
          <button onClick={() => photoRef.current?.click()} disabled={busy}
            style={{ width: '100%', padding: '0.65rem', background: 'rgba(255,255,255,0.03)', border: '1px dashed rgba(255,255,255,0.15)', borderRadius: 12, color: '#9ca3af', fontWeight: 700, fontSize: '0.78rem', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
            📷 Agregar foto de evidencia
          </button>
          <input ref={photoRef} type="file" accept="image/*" capture="environment" onChange={handleEvidenceFile} style={{ display: 'none' }} />
        </div>
      )}

      {/* Chips */}
      {chips.length > 0 && step !== STEP.DONE && (
        <div style={{ display: 'flex', gap: '0.4rem', padding: '0.4rem 0.75rem 0.25rem', overflowX: 'auto', flexShrink: 0, scrollbarWidth: 'none' }}>
          {chips.map(c => (
            <button key={c} onClick={() => handleChip(c)} disabled={busy}
              style={{ padding: '0.35rem 0.85rem', borderRadius: 20, flexShrink: 0, whiteSpace: 'nowrap', fontWeight: 700, fontSize: '0.72rem', cursor: 'pointer',
                border:      `1px solid ${cancelPending && c.startsWith('Sí') ? 'rgba(239,68,68,0.5)' : 'rgba(255,95,51,0.35)'}`,
                background:  cancelPending && c.startsWith('Sí') ? 'rgba(239,68,68,0.12)' : 'rgba(255,95,51,0.08)',
                color:       cancelPending && c.startsWith('Sí') ? '#ef4444' : '#ff8c5a',
              }}>
              {c}
            </button>
          ))}
        </div>
      )}

      {/* Barra de input */}
      {showInputBar && (
        <div style={{ background: '#13131a', borderTop: '1px solid rgba(255,255,255,0.06)', padding: '0.6rem 0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem', flexShrink: 0 }}>
          {step === STEP.PLATE && (
            <CameraInput mode="document" onResult={onDocumentPhoto} onError={msg => pushBot(msg)} disabled={busy} size={40} />
          )}
          {step === STEP.KM && (
            <CameraInput mode="odometer" onResult={onOdometerPhoto} onError={msg => pushBot(msg)} disabled={busy} size={40} />
          )}
          <input ref={inputRef} value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
            disabled={busy} placeholder={placeholders[step] || 'Escribí tu respuesta…'}
            style={{ flex: 1, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 22, padding: '0.6rem 0.9rem', color: '#fff', fontSize: '0.85rem', outline: 'none', minWidth: 0 }} />
          <VoiceInput onTranscript={onTranscript} onError={msg => pushBot(msg)} disabled={busy} size={40} />
          <button onClick={handleSend} disabled={busy || !input.trim()}
            style={{ width: 40, height: 40, borderRadius: '50%', border: 'none', background: input.trim() && !busy ? '#ff5f33' : 'rgba(255,255,255,0.06)', color: '#fff', fontSize: '1rem', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, transition: 'background 0.15s' }}>
            ↑
          </button>
        </div>
      )}

      <div style={{ height: '5rem', flexShrink: 0 }} />
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

// ─── Helpers ──────────────────────────────────────────────────────────────────
function bubbleStyle(role) {
  const isBot = role === 'bot';
  return {
    maxWidth: '82%', padding: '0.6rem 0.85rem',
    borderRadius: isBot ? '4px 18px 18px 18px' : '18px 4px 18px 18px',
    background: isBot ? '#1e1e2a' : 'rgba(255,95,51,0.18)',
    border: `1px solid ${isBot ? 'rgba(255,255,255,0.06)' : 'rgba(255,95,51,0.25)'}`,
    fontSize: '0.82rem', lineHeight: 1.45, color: isBot ? '#d1d1e0' : '#fff', wordBreak: 'break-word',
  };
}

function formatText(text) {
  if (!text) return null;
  return text.split('\n').map((line, i, arr) => {
    const parts = line.split(/(\*[^*]+\*)/g).map((p, j) =>
      p.startsWith('*') && p.endsWith('*')
        ? <strong key={j} style={{ color: '#fff', fontWeight: 800 }}>{p.slice(1, -1)}</strong>
        : p
    );
    return <span key={i}>{parts}{i < arr.length - 1 ? <br /> : null}</span>;
  });
}

const placeholders = {
  [STEP.PLATE]:             'Ej: ABC123',
  [STEP.CORRECTING_OCR]:    'Escribí la placa correcta',
  [STEP.ASKING_PHONE]:      'Ej: 3001234567',
  [STEP.EDITING_CLIENT_FIELD]: 'Nuevo valor…',
  [STEP.KM]:                'Ej: 12500',
  [STEP.ASKING_PHOTO_DESC]: 'Describí la foto…',
  [STEP.ACCESSORIES]:       'Casco, candado, alforjas…',
  [STEP.NOTES]:             '¿Qué trae la moto?',
  [STEP.INTAKE]:            'Tu respuesta…',
  [STEP.OBSERVATIONS]:      'Rayones, acuerdos…',
};
