import { formatDay, tratamiento } from './copy';

export function YaRespondidaScreen({ fecha }) {
  const day = formatDay(fecha);
  return (
    <div className="enc-body">
      <h1 className="enc-title">Ya recibimos tu calificación.</h1>
      <p className="enc-text">
        {day ? `Gracias por el tiempo que nos diste el ${day}.` : 'Gracias por el tiempo que nos diste.'}
      </p>
    </div>
  );
}

export function ClosingScreen({ clasificacion, casoNumero, nombre }) {
  if (clasificacion === 'DETRACTOR') {
    return (
      <div className="enc-closing is-dark">
        <div className="enc-closing-main">
          <h1 className="enc-title" style={{ marginTop: 0 }}>{`Gracias por decírnoslo, ${tratamiento(nombre)}.`}</h1>
          <p className="enc-text">Nuestro equipo de servicio al cliente te va a contactar.</p>
          <div className="enc-case">
            <div className="enc-step">TU CASO</div>
            <div className="enc-case-number">{`No. ${casoNumero}`}</div>
            <p>Queda registrado a tu nombre. Si nadie te contacta, este número es tu respaldo.</p>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="enc-closing">
      <div className="enc-closing-main">
        <h1 className="enc-title" style={{ marginTop: 0 }}>{`Gracias, ${tratamiento(nombre)}.`}</h1>
        <p className="enc-text">Tu opinión nos ayuda a mejorar.</p>
      </div>
      <div className="enc-band" aria-hidden="true" />
    </div>
  );
}
