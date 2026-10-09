/**
 * Join screen (prototype "IngresoPareja"): code, two members and the data
 * notice. Presentational only.
 */
import { C, MONO, botonPrimario, campo, pantalla, tarjeta } from './estilos';
import { TEXTOS } from './textos';

const etiqueta = { display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13, fontWeight: 700 };

function Integrante({ numero, datos, onCambio }) {
  return (
    <fieldset style={{ ...tarjeta, margin: 0, padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <legend style={{ fontSize: 13, fontWeight: 800, color: C.medio, padding: 0, float: 'left' }}>
        Integrante {numero}
      </legend>
      <label style={etiqueta}>
        Nombre completo
        <input
          type="text"
          autoComplete="off"
          placeholder="Nombre y apellido"
          value={datos.nombre}
          onChange={(e) => onCambio('nombre', e.target.value)}
          style={campo}
        />
      </label>
      <label style={etiqueta}>
        Cédula
        <input
          type="text"
          inputMode="numeric"
          autoComplete="off"
          placeholder="Solo números"
          value={datos.cedula}
          onChange={(e) => onCambio('cedula', e.target.value)}
          style={campo}
        />
      </label>
    </fieldset>
  );
}

function Mensaje({ texto, color, fondo }) {
  return (
    <div role="alert" style={{ padding: '12px 14px', borderRadius: 12, background: fondo, color, fontSize: 14 }}>
      {texto}
    </div>
  );
}

export default function IngresoPareja({
  codigo, integrantes, error, aviso, huerfanas, enviando, onCodigo, onIntegrante, onEnviar,
}) {
  return (
    <form onSubmit={onEnviar} noValidate style={{ ...pantalla, maxWidth: 520, margin: '0 auto', width: '100%' }}>
      <header style={{ padding: '20px 20px 16px', background: C.tinta, color: C.blanco, display: 'flex', flexDirection: 'column', gap: 4 }}>
        <span style={{ fontWeight: 800, fontSize: 18 }}>Motored</span>
        <span style={{ fontSize: 15, color: C.borde }}>Conteo total</span>
      </header>
      <div style={{ flex: 1, padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800 }}>Ingreso de la pareja</h1>
        {aviso && <Mensaje texto={aviso} color={C.alerta} fondo={C.alertaFondo} />}
        {huerfanas > 0 && (
          <Mensaje
            color={C.alerta}
            fondo={C.alertaFondo}
            texto={`Este equipo tiene ${huerfanas} lecturas de una sesión anterior que no se alcanzaron a enviar. Avise al líder del conteo antes de ingresar.`}
          />
        )}
        <label style={{ ...etiqueta, fontSize: 14, gap: 6 }}>
          Código del conteo
          <input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={codigo}
            onChange={(e) => onCodigo(e.target.value)}
            style={{ ...campo, fontFamily: MONO, fontSize: 24, letterSpacing: '0.1em', padding: '12px 14px' }}
          />
        </label>
        {integrantes.map((datos, n) => (
          <Integrante key={n} numero={n + 1} datos={datos} onCambio={(c, v) => onIntegrante(n, c, v)} />
        ))}
        <div style={{ fontSize: 12, color: C.medio }}>{TEXTOS.avisoDatos}</div>
        {error && <Mensaje texto={error} color={C.critico} fondo={C.criticoFondo} />}
      </div>
      <div style={{ padding: '16px 20px 24px', background: C.blanco, borderTop: `1px solid ${C.borde}` }}>
        <button type="submit" disabled={enviando} style={{ ...botonPrimario, opacity: enviando ? 0.6 : 1 }}>
          Empezar a contar
        </button>
      </div>
    </form>
  );
}
