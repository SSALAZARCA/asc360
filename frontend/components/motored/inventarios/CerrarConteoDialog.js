'use client';
/**
 * Close confirm (WU12). Warns about connected pairs silent for too long
 * (they may hold unsent readings; the leader can still close). A 409
 * RECONTEOS_ABIERTOS turns it into the forced close: the open counts, and
 * a required reason (the open reconteos are cancelled).
 */
import { useState } from 'react';
import DialogoPedido from '../pedidos/DialogoPedido';
import InfoTooltip from '../InfoTooltip';
import { cerrarConteo } from '../../../lib/motored/conteosApi';
import { parejaCorta } from './conteosFormato';
import { AYUDA_FORZAR } from './ayudas';
import { avisoStyle, labelStyle } from './estilos';

function AvisoInactivas({ inactivas }) {
  if (inactivas.length === 0) return null;
  return (
    <div style={avisoStyle('warning')}>
      <div>
        <ul style={{ margin: 0, paddingLeft: '1.1rem' }}>
          {inactivas.map(({ sesion, minutos }) => (
            <li key={sesion.id}>{`La ${parejaCorta(sesion.etiqueta)} lleva ${minutos} minutos sin enviar lecturas.`}</li>
          ))}
        </ul>
        <div>Puede tener lecturas guardadas sin enviar. ¿Cerrar igual?</div>
      </div>
    </div>
  );
}

export default function CerrarConteoDialog({ conteoId, inactivas = [], onCancel, onCerrado }) {
  const [abiertos, setAbiertos] = useState(null);
  const [motivo, setMotivo] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState('');
  const forzando = abiertos != null;

  const confirmar = async () => {
    setOcupado(true);
    setError('');
    try {
      await cerrarConteo(conteoId, forzando ? { forzar: true, motivo: motivo.trim() } : { forzar: false });
      onCerrado();
    } catch (err) {
      if (err.code === 'RECONTEOS_ABIERTOS' && !forzando) {
        setAbiertos({ pendientes: err.datos?.pendientes ?? 0, asignados: err.datos?.asignados ?? 0 });
      } else {
        setError(err.message || 'No se pudo cerrar el conteo.');
      }
      setOcupado(false);
    }
  };

  const descripcion = forzando ? (
    <span>
      {`Todavía hay reconteos abiertos: quedan ${abiertos.pendientes} sin asignar y ${abiertos.asignados} asignados. `}
      Puede esperar a que terminen o forzar el cierre: esos reconteos se cancelan y cuenta lo de la primera vuelta.
    </span>
  ) : (
    <span>Al cerrar se calcula el resultado y la exactitud, se genera la lista de ajustes y el enlace de las parejas deja de funcionar.</span>
  );

  return (
    <DialogoPedido
      titulo="Cerrar conteo" descripcion={descripcion} error={error} ocupado={ocupado}
      textoConfirmar={forzando ? 'Forzar cierre' : 'Cerrar conteo'}
      confirmarDeshabilitado={forzando && motivo.trim() === ''} onConfirm={confirmar} onCancel={onCancel}
    >
      <AvisoInactivas inactivas={inactivas} />
      {forzando && (
        <div style={labelStyle}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
            <label htmlFor="motivo-cierre-forzado">Motivo del cierre forzado</label>
            <InfoTooltip text={AYUDA_FORZAR} />
          </span>
          <textarea id="motivo-cierre-forzado" rows={3} maxLength={2000} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
        </div>
      )}
    </DialogoPedido>
  );
}
