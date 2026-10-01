'use client';
/** One cap per tienda. With `editable` each row has a field (empty = sin tope); without it the caps are plain text. */
import InfoTooltip from '../InfoTooltip';
import MotoredTableScroll from '../MotoredTableScroll';
import { formatCOP } from '../../../lib/motored/formatCOP';
import { TOPE_TEXTO } from './TopeBanner';
import { fechaCorta } from './reglas';
import { errorStyle, mutedStyle, numStyle, stickyColStyle, stickyHeadStyle, tablaStyle, tdStyle, thStyle } from './styles';
import { parsearTope, topeComoTexto } from './tope';

const inputStyle = {
  width: '11rem', height: '44px', boxSizing: 'border-box', padding: '0 8px', textAlign: 'right',
  fontSize: '16px', fontVariantNumeric: 'tabular-nums',
};

function Cabecera({ editable }) {
  return (
    <thead>
      <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
        <th style={{ ...thStyle, ...stickyHeadStyle, ...stickyColStyle, zIndex: 4, top: 0 }}>Tienda</th>
        <th style={{ ...thStyle, ...stickyHeadStyle }}>
          <span style={{ display: 'inline-flex', alignItems: 'center' }}>Tope actual<InfoTooltip text={TOPE_TEXTO} /></span>
        </th>
        <th style={{ ...thStyle, ...stickyHeadStyle }}>Vigente desde</th>
        {editable && <th style={{ ...thStyle, ...stickyHeadStyle }}>Nuevo tope (pesos)</th>}
      </tr>
    </thead>
  );
}

function Campo({ tope, texto, error, onCambiar }) {
  const valor = texto ?? topeComoTexto(tope.valor);
  const { valor: pesos } = parsearTope(valor);
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: '2px' }}>
      <input
        type="text" inputMode="numeric" autoComplete="off" placeholder="Sin tope" style={inputStyle}
        aria-label={`Tope de ${tope.nombre}`} aria-invalid={error ? 'true' : undefined} value={valor}
        onChange={(e) => onCambiar(tope.sucursal_id, e.target.value)} onFocus={(e) => e.target.select()}
      />
      {error && <span role="alert" style={{ ...errorStyle, whiteSpace: 'normal', maxWidth: '16rem' }}>{error}</span>}
      {!error && pesos != null && valor !== topeComoTexto(tope.valor) && <span style={mutedStyle}>{formatCOP(pesos)}</span>}
    </span>
  );
}

function Fila({ tope, editable, texto, error, onCambiar }) {
  return (
    <tr style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
      <td style={{ ...tdStyle, ...stickyColStyle, fontWeight: 600 }}>{tope.nombre}</td>
      <td style={{ ...tdStyle, ...numStyle }}>{tope.valor == null ? <span style={mutedStyle}>Sin tope</span> : formatCOP(tope.valor)}</td>
      <td style={tdStyle}>{tope.vigente_desde ? fechaCorta(tope.vigente_desde) : <span style={mutedStyle}>—</span>}</td>
      {editable && <td style={tdStyle}><Campo tope={tope} texto={texto} error={error} onCambiar={onCambiar} /></td>}
    </tr>
  );
}

export default function TopesTable({ topes, editable, textos, errores, onCambiar }) {
  return (
    <MotoredTableScroll maxHeight="70vh">
      <table aria-label="Topes por tienda" style={{ ...tablaStyle, width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <Cabecera editable={editable} />
        <tbody>
          {topes.map((t) => (
            <Fila key={t.sucursal_id} tope={t} editable={editable} texto={textos[t.sucursal_id]} error={errores[t.sucursal_id]} onCambiar={onCambiar} />
          ))}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}
