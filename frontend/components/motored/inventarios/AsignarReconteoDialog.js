'use client';
/**
 * Assign a reconteo to a connected pair (WU12). The backend decides
 * eligibility (no shared cédula with the first round): MISMA_PAREJA and
 * HAY_PAREJA_ELEGIBLE come back with their message. Only when exactly one
 * pair is connected the leader may authorize that same pair, with a reason.
 */
import { useState } from 'react';
import DialogoPedido from '../pedidos/DialogoPedido';
import { asignarReconteo } from '../../../lib/motored/conteosApi';
import { labelStyle, optionStyle, selectStyle } from './estilos';

export default function AsignarReconteoDialog({ conteoId, fila, sesiones, onCancel, onListo }) {
  const conectadas = sesiones.filter((s) => s.estado === 'CONECTADA');
  const [sesionId, setSesionId] = useState('');
  const [rechazo, setRechazo] = useState('');
  const [autorizar, setAutorizar] = useState(false);
  const [motivo, setMotivo] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState('');
  const ofreceAutorizar = rechazo === 'MISMA_PAREJA' && conectadas.length === 1;

  const confirmar = async () => {
    setOcupado(true);
    setError('');
    const cuerpo = autorizar
      ? { sesion_id: sesionId, autorizar_misma_pareja: true, motivo: motivo.trim() }
      : { sesion_id: sesionId };
    try {
      await asignarReconteo(conteoId, fila.reconteo.id, cuerpo);
      onListo();
    } catch (err) {
      setRechazo(err.code || '');
      setError(err.message || 'No se pudo asignar el reconteo.');
      setOcupado(false);
    }
  };

  return (
    <DialogoPedido
      titulo={`Asignar reconteo · ${fila.codigo}`}
      descripcion={<span>El reconteo lo hace otra pareja: nunca quien contó esta referencia en la primera vuelta.</span>}
      error={error} ocupado={ocupado} textoConfirmar="Asignar"
      confirmarDeshabilitado={!sesionId || (autorizar && motivo.trim() === '')}
      onConfirm={confirmar} onCancel={onCancel}
    >
      <label style={labelStyle}>
        Pareja
        <select value={sesionId} onChange={(e) => setSesionId(e.target.value)} style={selectStyle}>
          <option value="" style={optionStyle}>Elija una pareja conectada</option>
          {conectadas.map((s) => <option key={s.id} value={s.id} style={optionStyle}>{s.etiqueta}</option>)}
        </select>
      </label>
      {ofreceAutorizar && (
        <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', fontSize: '0.85rem', minHeight: '44px' }}>
          <input type="checkbox" checked={autorizar} onChange={(e) => setAutorizar(e.target.checked)} />
          Autorizar misma pareja (es la única conectada)
        </label>
      )}
      {ofreceAutorizar && autorizar && (
        <label style={labelStyle}>
          Motivo de la autorización
          <textarea rows={2} maxLength={2000} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
        </label>
      )}
    </DialogoPedido>
  );
}
