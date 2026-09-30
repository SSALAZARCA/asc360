'use client';
import EncuestaShell from './EncuestaShell';
import { CedulaScreen, PlacaScreen } from './IdentityScreens';
import { ConsentScreen, MatrixScreen, ObservacionesScreen, ScaleScreen } from './QuestionScreens';
import { ClosingScreen, YaRespondidaScreen } from './EndScreens';
import buildFooter from './buildFooter';
import useEncuestaFlow from './useEncuestaFlow';
import useOnlineStatus from './useOnlineStatus';

const QUESTION_STEPS = { q1: 1, q2: 2, q3: 3, q4: 4 };

/** Wires the flow hook to the presentational screens. */
export default function EncuestaContainer({ fontClassName }) {
  const flow = useEncuestaFlow();
  const offline = useOnlineStatus();
  const { step, answers, cliente, closing } = flow;

  return (
    <EncuestaShell
      fontClassName={fontClassName}
      offline={offline}
      progress={QUESTION_STEPS[step] ? QUESTION_STEPS[step] / 4 : null}
      footer={buildFooter(step, flow)}
    >
      {step === 'cedula' && (
        <CedulaScreen
          cedula={flow.cedula}
          onChange={flow.setCedula}
          celular4={flow.celular4}
          onChangeCelular4={flow.setCelular4}
          onSubmit={flow.submitCedula}
          error={flow.error}
        />
      )}
      {step === 'placa' && <PlacaScreen nombre={cliente.nombre} registros={cliente.registros} onPick={flow.pickRegistro} />}
      {step === 'q1' && <ScaleScreen nombre={cliente.nombre} value={answers.q1} onChange={answers.setQ1} />}
      {step === 'q2' && <MatrixScreen answers={answers.matrix} onAnswer={answers.answerMatrix} />}
      {step === 'q3' && <ObservacionesScreen value={answers.observaciones} onChange={answers.setObservaciones} />}
      {step === 'q4' && (
        <ConsentScreen
          value={answers.consent}
          onChange={flow.chooseConsent}
          busy={flow.busy}
          error={flow.error}
          onRetry={flow.retry}
        />
      )}
      {step === 'ya' && <YaRespondidaScreen fecha={flow.fecha} />}
      {step === 'closing' && (
        <ClosingScreen clasificacion={closing.clasificacion} casoCodigo={closing.caso_codigo} nombre={closing.primer_nombre} />
      )}
    </EncuestaShell>
  );
}
