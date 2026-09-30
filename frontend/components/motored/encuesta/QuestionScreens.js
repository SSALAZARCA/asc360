import ChoiceGroup from './ChoiceGroup';
import { COPY, MATRIX_ROWS, SCALE_WORDS, tratamiento } from './copy';

const SCALE = [1, 2, 3, 4, 5].map((n) => ({ value: n, label: String(n) }));
const MATRIX_OPTIONS = [...SCALE, { value: 'NS', label: 'NS/NR', className: 'enc-na' }];
export const OBSERVACIONES_MAX = 2000;
const OBSERVACIONES_WARN = 1900;

const Heading = ({ step, greeting, children }) => (
  <>
    {greeting && <p className="enc-greeting">{greeting}</p>}
    <div className="enc-step">{`PREGUNTA ${step} DE 4`}</div>
    {children}
  </>
);

export function ScaleScreen({ nombre, value, onChange }) {
  return (
    <div className="enc-body">
      <Heading step={1} greeting={`Hola, ${tratamiento(nombre)}.`}>
        <h1 className="enc-question">{COPY.q1}</h1>
      </Heading>
      <ChoiceGroup label={COPY.q1} options={SCALE} value={value} onChange={onChange} className="enc-scale" />
      <div className="enc-ends">
        <span>MUY INSATISFECHO</span>
        <span>MUY SATISFECHO</span>
      </div>
      <div className="enc-word" aria-live="polite">{value ? SCALE_WORDS[value] : ''}</div>
    </div>
  );
}

export function MatrixScreen({ answers, onAnswer }) {
  const done = answers.filter((a) => a != null).length;
  return (
    <div className="enc-body">
      <Heading step={2}>
        <h1 className="enc-question" style={{ fontSize: 17, lineHeight: '27px' }}>{COPY.q2Intro}</h1>
      </Heading>
      <div className="enc-legend">
        <span>1 Pésimo · 5 Excelente</span>
        <span>{`${done}/6`}</span>
      </div>
      <div className="enc-cards">
        {MATRIX_ROWS.map(([key, text], i) => (
          <div key={key} className={`enc-card-row ${answers[i] != null ? 'is-done' : ''}`}>
            <p>{text}</p>
            <ChoiceGroup
              label={text}
              options={MATRIX_OPTIONS}
              value={answers[i]}
              onChange={(v) => onAnswer(i, v)}
              className="enc-matrix"
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export function ObservacionesScreen({ value, onChange }) {
  const warn = value.length > OBSERVACIONES_WARN;
  return (
    <div className="enc-body">
      <Heading step={3}>
        <label className="enc-question" htmlFor="enc-observaciones">{COPY.q3}</label>
      </Heading>
      <textarea
        id="enc-observaciones"
        className="enc-textarea"
        rows={6}
        maxLength={OBSERVACIONES_MAX}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <div className={`enc-counter ${warn ? 'is-warning' : ''}`}>{`${value.length} / ${OBSERVACIONES_MAX}`}</div>
    </div>
  );
}

const YES_NO = [
  { value: true, label: 'Sí' },
  { value: false, label: 'No' },
];

export function ConsentScreen({ value, onChange, busy, error, onRetry }) {
  return (
    <div className="enc-body">
      <Heading step={4}>
        <h1 className="enc-question" style={{ fontSize: 17, lineHeight: '27px' }}>{COPY.q4}</h1>
      </Heading>
      <ChoiceGroup label={COPY.q4} options={YES_NO} value={value} onChange={onChange} className="enc-yesno" disabled={busy} />
      {error && (
        <>
          <p className="enc-error" role="alert">{error}</p>
          <button type="button" className="enc-retry" onClick={onRetry}>Reintentar</button>
        </>
      )}
    </div>
  );
}
