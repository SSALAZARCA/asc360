'use client';
/**
 * "Cantidad a pedir" of a line: the number (or `entrada`, the editable input),
 * a dot with who edited it (and the history button), the pack-multiple warning
 * and `aviso` (the editing error) underneath.
 */
import InfoTooltip from '../InfoTooltip';
import MotoredIconAction from '../MotoredIconAction';
import { fechaHora, unidades } from './formato';
import { errorStyle } from './styles';

const warnStyle = {
  fontSize: '0.7rem', color: 'var(--motored-warning, #d97706)', fontWeight: 600,
  whiteSpace: 'normal', maxWidth: '170px',
};

/** The editing error of a line, under its quantity (also shown when the pedido stopped being editable). */
export function AvisoCantidad({ id, mensaje }) {
  if (!mensaje) return null;
  return <span id={id} role="alert" style={{ ...errorStyle, whiteSpace: 'normal', maxWidth: '190px' }}>{mensaje}</span>;
}

export default function CantidadCelda({ linea, onHistorial, entrada, aviso }) {
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '2px' }}>
        {entrada ?? <span style={{ fontWeight: 700 }}>{unidades(linea.pedido_final)}</span>}
        {linea.editada && (
          <>
            <span aria-hidden="true" style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--motored-primary, #e20714)' }} />
            <InfoTooltip text={`Editado por ${linea.editado_por} el ${fechaHora(linea.editado_en)}`} />
            <MotoredIconAction
              action="Historial" label={`Historial de la línea ${linea.codigo_referencia}`} touch
              onClick={() => onHistorial(linea)}
            />
          </>
        )}
      </span>
      {linea.fuera_de_empaque && <span style={warnStyle}>{`No es múltiplo del empaque (${linea.unidad_empaque})`}</span>}
      {aviso}
    </span>
  );
}
