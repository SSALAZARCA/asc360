'use client';
/**
 * "3. Acceso para las parejas" (WU11): the QR (fetched with the token), the
 * 6-digit code only right after start or rotation ("Código oculto"
 * afterwards: the API never returns it again), the link with a copy button,
 * and the print / rotate buttons. GERENCIA never gets the access block.
 */
import { useEffect, useState } from 'react';
import { obtenerQrObjectUrl } from '../../../lib/motored/conteosApi';
import { ESTADOS_ABIERTOS, formatCodigo } from './conteosFormato';
import { imprimirEtiquetas, imprimirQr } from './imprimir';
import { cardStyle, errorStyle, h2Style, monoStyle, mutedStyle, pildoraStyle } from './estilos';

const botonStyle = { minHeight: '44px' };
const rotulo = { fontSize: '0.8rem', fontWeight: 700, color: 'var(--motored-text-muted, #5a5a5a)' };

function useQr(conteoId, activo) {
  const [src, setSrc] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    if (!activo) return undefined;
    let vivo = true;
    let creado = '';
    obtenerQrObjectUrl(conteoId)
      .then((url) => { creado = url; if (vivo) setSrc(url); })
      .catch((err) => { if (vivo) setError(err.message || 'No se pudo cargar el QR.'); });
    return () => {
      vivo = false;
      if (creado && URL.revokeObjectURL) URL.revokeObjectURL(creado);
    };
  }, [conteoId, activo]);
  return { src, error };
}

function Codigo({ codigo }) {
  if (codigo) return <div style={{ ...monoStyle, fontSize: '2.5rem', fontWeight: 600, letterSpacing: '0.1em' }}>{formatCodigo(codigo)}</div>;
  return <div style={{ ...mutedStyle, fontSize: '1rem' }}>Código oculto</div>;
}

function Enlace({ url }) {
  const [copiado, setCopiado] = useState(false);
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopiado(true);
    } catch {
      setCopiado(false);
    }
  };
  if (!url) return <div style={errorStyle}>El enlace público no está configurado. Avise al administrador.</div>;
  return (
    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
      <span style={{ ...monoStyle, padding: '10px 12px', borderRadius: '8px', background: 'var(--motored-surface-alt, #f4f4f5)', wordBreak: 'break-all' }}>{url}</span>
      <button type="button" className="motored-btn motored-btn-secondary" style={botonStyle} onClick={copiar}>Copiar enlace</button>
      {copiado && <span style={mutedStyle} role="status">Copiado</span>}
    </div>
  );
}

export default function AccesoParejas({ conteo, permisos, acceso, ubicaciones }) {
  const abierto = ESTADOS_ABIERTOS.includes(conteo.estado) && Boolean(conteo.acceso);
  const qr = useQr(conteo.id, abierto && permisos.opera);
  const tienda = conteo.sucursal.nombre;
  if (!permisos.opera) return null;

  return (
    <div style={{ ...cardStyle, flex: '1 1 520px', gap: '1.1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
        <h2 style={h2Style}>3. Acceso para las parejas</h2>
        {abierto && <span style={pildoraStyle('var(--motored-success-bg, #ecfdf3)', 'var(--motored-success, #15803d)')}>Conteo abierto</span>}
      </div>
      {!abierto && <p style={{ ...mutedStyle, margin: 0 }}>El QR, el enlace y el código aparecen al iniciar el conteo.</p>}
      {abierto && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.5rem', alignItems: 'center' }}>
          <div style={{ width: '220px', height: '220px', border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: '12px', display: 'grid', placeItems: 'center', background: '#ffffff' }}>
            {qr.src ? <img src={qr.src} alt="Código QR del conteo" style={{ width: '200px', height: '200px' }} /> : <span style={mutedStyle}>{qr.error || 'Cargando QR…'}</span>}
          </div>
          <div style={{ flex: '1 1 240px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
            <div><div style={rotulo}>Código del conteo</div><Codigo codigo={acceso.codigo} /></div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              <div style={rotulo}>Enlace para portátiles</div>
              <Enlace url={conteo.acceso.url} />
            </div>
          </div>
        </div>
      )}
      {abierto && (
        <ol style={{ margin: 0, paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.95rem' }}>
          <li>Cada pareja escanea el QR con el celular, o abre el enlace en su portátil.</li>
          <li>Escribe el código del conteo y los nombres y cédulas de los dos integrantes.</li>
          <li>Cada celular o portátil queda como una pareja. Un solo QR sirve para todas.</li>
        </ol>
      )}
      <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
        {abierto && (
          <button type="button" className="motored-btn motored-btn-secondary" style={botonStyle} disabled={!qr.src}
            onClick={() => imprimirQr({ tienda, qrSrc: qr.src, url: conteo.acceso.url })}>
            Imprimir QR
          </button>
        )}
        <button type="button" className="motored-btn motored-btn-secondary" style={botonStyle}
          disabled={!ubicaciones.some((u) => u.activa)} onClick={() => imprimirEtiquetas({ tienda, ubicaciones })}>
          Imprimir etiquetas de ubicación
        </button>
        {abierto && <button type="button" className="motored-btn motored-btn-secondary" style={botonStyle} onClick={acceso.rotar}>Cambiar código</button>}
      </div>
      {acceso.error && <p role="alert" style={errorStyle}>{acceso.error}</p>}
      <div style={mutedStyle}>
        El código y el enlace dejan de funcionar al cerrar el conteo. Cambiar el código no saca a las parejas que ya están contando.
      </div>
    </div>
  );
}
