'use client';
/**
 * "Cantidad a pedir" of a line, read-only for now: the number, a dot with who
 * edited it (and the history button), and the pack-multiple warning.
 */
import InfoTooltip from '../InfoTooltip';
import MotoredIconAction from '../MotoredIconAction';
import { fechaHora, unidades } from './formato';

const warnStyle = {
  fontSize: '0.7rem', color: 'var(--motored-warning, #d97706)', fontWeight: 600,
  whiteSpace: 'normal', maxWidth: '170px',
};

export default function CantidadCelda({ linea, onHistorial }) {
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '2px' }}>
        <span style={{ fontWeight: 700 }}>{unidades(linea.pedido_final)}</span>
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
    </span>
  );
}
