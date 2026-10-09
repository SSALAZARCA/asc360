/**
 * Feedback under the scanner: the unknown-code message from the prototype
 * (with "Registrar de todas formas"), the location-first prompt, errors,
 * and readings the server refused. Plus the offline / pending banner.
 */
import { C } from './estilos';
import { TEXTOS, textoPendientes } from './textos';

const caja = {
  display: 'flex', gap: 12, alignItems: 'flex-start', padding: '14px 18px', borderRadius: 12,
  background: C.criticoFondo, border: `1px solid ${C.criticoBorde}`, color: C.critico, fontSize: 14,
};

function IconoError() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={C.critico} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flexShrink: 0 }}>
      <circle cx="12" cy="12" r="10" />
      <path d="M15 9l-6 6" />
      <path d="M9 9l6 6" />
    </svg>
  );
}

export function AvisoLectura({ aviso, onForzar }) {
  if (!aviso) return null;
  if (aviso.tipo === 'desconocido') {
    return (
      <div role="alert" style={{ ...caja, flexWrap: 'wrap' }}>
        <IconoError />
        <div style={{ flex: '1 1 240px' }}>
          <span style={{ fontWeight: 800 }}>{`Código no encontrado: ${aviso.codigo}.`}</span>
          {' Revise la etiqueta o escríbalo a mano. No se sumó nada.'}
        </div>
        <button
          type="button"
          onClick={onForzar}
          style={{ fontFamily: 'inherit', fontSize: 13, fontWeight: 800, padding: '8px 12px', borderRadius: 10, border: `1px solid ${C.critico}`, background: C.blanco, color: C.critico, cursor: 'pointer' }}
        >
          Registrar de todas formas
        </button>
      </div>
    );
  }
  return (
    <div role="alert" style={caja}>
      <IconoError />
      <div>{aviso.texto}</div>
    </div>
  );
}

export function Rechazos({ rechazos }) {
  if (!rechazos.length) return null;
  return (
    <div role="status" style={{ ...caja, flexDirection: 'column', gap: 4 }}>
      <div style={{ fontWeight: 800 }}>Lecturas que no se registraron</div>
      {rechazos.map((r) => (
        <div key={r.id}>{`${r.codigo}: ${r.texto}.`}</div>
      ))}
    </div>
  );
}

export function BannerPendientes({ sinConexion, pendientes }) {
  if (!sinConexion && !pendientes) return null;
  let texto = textoPendientes(pendientes);
  if (sinConexion) texto = pendientes ? `Sin conexión · ${texto}` : 'Sin conexión';
  return (
    <div
      role="status"
      style={{ padding: '10px 16px', background: sinConexion ? C.alertaFondo : C.fondo, color: sinConexion ? C.alerta : C.medio, fontSize: 14, fontWeight: 700, borderBottom: `1px solid ${C.borde}` }}
    >
      {texto}
    </div>
  );
}

export function NotaRonda({ estado, tarea }) {
  if (estado !== 'EN_RECONTEO' || tarea) return null;
  return (
    <div style={{ padding: '12px 16px', borderRadius: 12, background: C.alertaFondo, color: C.alerta, fontSize: 14, fontWeight: 700 }}>
      {TEXTOS.rondaTerminada}
    </div>
  );
}
