import { COPY } from './copy';

export function CedulaScreen({ cedula, onChange, celular4, onChangeCelular4, onSubmit, error }) {
  return (
    <div className="enc-body">
      <p className="enc-text" style={{ marginTop: 8 }}>{COPY.intro}</p>
      <label className="enc-question" htmlFor="enc-cedula" style={{ marginTop: 22 }}>
        {COPY.cedulaQuestion}
      </label>
      <p className="enc-hint">{COPY.cedulaHint}</p>
      <input
        id="enc-cedula"
        className="enc-input"
        type="text"
        inputMode="numeric"
        autoComplete="off"
        value={cedula}
        onChange={(e) => onChange(e.target.value.replace(/[^\d.\s-]/g, ''))}
        onKeyDown={(e) => e.key === 'Enter' && onSubmit()}
      />
      <label className="enc-question" htmlFor="enc-celular4" style={{ marginTop: 22 }}>
        {COPY.celularQuestion}
      </label>
      <p className="enc-hint">{COPY.celularHint}</p>
      <input
        id="enc-celular4"
        className="enc-input"
        type="text"
        inputMode="numeric"
        maxLength={4}
        autoComplete="off"
        value={celular4}
        onChange={(e) => onChangeCelular4(e.target.value.replace(/\D/g, '').slice(0, 4))}
        onKeyDown={(e) => e.key === 'Enter' && onSubmit()}
      />
      {error && <p className="enc-error" role="alert">{error}</p>}
    </div>
  );
}

export function PlacaScreen({ nombre, registros, onPick }) {
  return (
    <div className="enc-body">
      <p className="enc-greeting">{`Hola, ${nombre}.`}</p>
      <h1 className="enc-question">{COPY.pickBike}</h1>
      <div className="enc-options">
        {registros.map((r) => (
          <button key={r.registro_id} type="button" className="enc-option" onClick={() => onPick(r.registro_id)}>
            <strong>{r.placa}</strong>
            <span>{r.linea}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
