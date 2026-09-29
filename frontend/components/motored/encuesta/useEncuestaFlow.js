import { useEffect, useRef, useState } from 'react';
import { COPY } from './copy';
import { enviarRespuesta, identificar } from './encuestaApi';
import { buildPayload } from './buildPayload';
import useSurveyAnswers from './useSurveyAnswers';

const AUTO_ADVANCE_MS = 190;
const BACK_STEP = { placa: 'cedula', q2: 'q1', q3: 'q2', q4: 'q3' };

// Maps an /identificar outcome to the next screen and the state it needs.
function routeIdentification(result, actions) {
  const { setError, setFecha, setCliente, setRegistroId, setStep } = actions;
  if (result.kind === 'rate') return setError(COPY.rateLimited);
  if (result.kind === 'network') return setError(COPY.network);
  if (result.kind !== 'ok') return setError(COPY.genericIdentify);
  const { estado, mensaje, respondida_at: at, primer_nombre: nombre, registros } = result.data;
  if (estado === 'NO_ENCONTRADA') return setError(mensaje);
  if (estado === 'YA_RESPONDIDA') {
    setFecha(at);
    return setStep('ya');
  }
  setCliente({ nombre, registros });
  if (registros.length === 1) setRegistroId(registros[0].registro_id);
  return setStep(registros.length === 1 ? 'q1' : 'placa');
}

// Maps a /respuestas outcome to the next screen.
function routeSubmission(result, actions) {
  const { setError, setClosing, setStep } = actions;
  if (result.kind === 'ok') {
    setClosing(result.data);
    return setStep('closing');
  }
  if (result.kind === 'conflict') return setStep('ya');
  if (result.kind === 'notfound') {
    setError(COPY.submitLost);
    return setStep('cedula');
  }
  return setError(result.kind === 'network' ? COPY.network : COPY.submitFailed);
}

/** State machine and API calls of the public survey. */
export default function useEncuestaFlow() {
  const [step, setStep] = useState('cedula');
  const [cedula, setCedula] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [cliente, setCliente] = useState({ nombre: '', registros: [] });
  const [registroId, setRegistroId] = useState(null);
  const [fecha, setFecha] = useState(null);
  const [closing, setClosing] = useState(null);
  const answers = useSurveyAnswers();
  const sending = useRef(false);
  const timer = useRef(null);
  const actions = { setError, setFecha, setCliente, setRegistroId, setStep, setClosing };

  useEffect(() => () => clearTimeout(timer.current), []);

  const submitCedula = async () => {
    if (!cedula.trim() || busy) return;
    setBusy(true);
    setError('');
    const result = await identificar(cedula.trim());
    setBusy(false);
    routeIdentification(result, actions);
  };

  const submit = async (autoriza) => {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setError('');
    const result = await enviarRespuesta(buildPayload({ cedula, registroId, ...answers }, autoriza));
    sending.current = false;
    setBusy(false);
    routeSubmission(result, actions);
  };

  const chooseConsent = (value) => {
    if (sending.current) return;
    answers.setConsent(value);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => submit(value), AUTO_ADVANCE_MS);
  };

  const goBack = () => {
    setError('');
    setStep(step === 'q1' ? (cliente.registros.length > 1 ? 'placa' : 'cedula') : BACK_STEP[step]);
  };

  const pickRegistro = (id) => {
    setRegistroId(id);
    setStep('q1');
  };

  return {
    step, setStep, cedula, setCedula, error, busy, cliente, fecha, closing, answers,
    submitCedula, chooseConsent, retry: () => submit(answers.consent), goBack, pickRegistro,
  };
}
