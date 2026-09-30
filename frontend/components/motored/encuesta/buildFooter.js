import { MATRIX_ROWS } from './copy';

/**
 * Pure footer config per step: { onBack?, helper?, cta? }. `flow` is the
 * useEncuestaFlow result; steps without a footer (ya, closing) return undefined.
 */
export default function buildFooter(step, flow) {
  const { cedula, celular4, busy, answers, submitCedula, goBack, setStep } = flow;
  const missing = answers.matrix.filter((a) => a == null).length;
  const footers = {
    cedula: { cta: { label: 'Continuar', disabled: !cedula.trim() || celular4.length !== 4 || busy, onClick: submitCedula } },
    placa: { onBack: goBack },
    q1: {
      onBack: goBack,
      helper: answers.q1 ? null : 'Elige una opción para continuar.',
      cta: { label: 'Continuar', disabled: !answers.q1, onClick: () => setStep('q2') },
    },
    q2: {
      onBack: goBack,
      cta: {
        label: missing ? `Faltan ${missing} de ${MATRIX_ROWS.length}` : 'Continuar',
        disabled: missing > 0,
        onClick: () => setStep('q3'),
      },
    },
    q3: {
      onBack: goBack,
      cta: { label: answers.observaciones.trim() ? 'Continuar' : 'Seguir sin escribir', onClick: () => setStep('q4') },
    },
    q4: { onBack: goBack },
  };
  return footers[step];
}
