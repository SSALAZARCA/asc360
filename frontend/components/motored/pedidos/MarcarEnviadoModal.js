'use client';
/** Mark one or several closed tiendas as sent: each one has its own HMCL order number and send date. */
import { useMemo, useState } from 'react';
import InfoTooltip from '../InfoTooltip';
import DialogoPedido from './DialogoPedido';
import { hoyBogota, validarEnvio } from './acciones';
import { plural } from './formato';
import { errorStyle, labelStyle, mutedStyle } from './styles';

const ORDEN_TEXTO = 'Orden de pedido: el número que HMCL le dio a este pedido al recibirlo. Cada tienda tiene el suyo.';

function FilaEnvio({ tienda, valor, rango, onCambio }) {
  const mensaje = valor.numero.trim() === '' ? '' : validarEnvio(valor, rango);
  return (
    <fieldset style={{ border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: '6px', padding: '0.75rem', margin: 0 }}>
      <legend style={{ fontWeight: 600, fontSize: '0.85rem' }}>{tienda.nombre}</legend>
      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '4px', flex: '1 1 180px' }}>
          <label style={{ ...labelStyle, flex: 1 }}>
            Número de orden
            <input
              aria-label={`Número de orden de ${tienda.nombre}`} maxLength={50} value={valor.numero}
              onChange={(e) => onCambio({ ...valor, numero: e.target.value })}
            />
          </label>
          <InfoTooltip text={ORDEN_TEXTO} />
        </div>
        <label style={labelStyle}>
          Fecha de envío
          <input
            type="date" aria-label={`Fecha de envío de ${tienda.nombre}`} value={valor.fecha}
            min={rango.desde} max={rango.hasta} onChange={(e) => onCambio({ ...valor, fecha: e.target.value })}
          />
        </label>
      </div>
      {mensaje && <p style={{ ...errorStyle, marginTop: '0.4rem' }}>{mensaje}</p>}
    </fieldset>
  );
}

export default function MarcarEnviadoModal({ tiendas, fechaCorte, ocupado, error, onConfirm, onCancel }) {
  const rango = useMemo(() => ({ desde: String(fechaCorte).slice(0, 10), hasta: hoyBogota() }), [fechaCorte]);
  const [valores, setValores] = useState(() => Object.fromEntries(tiendas.map((t) => [t.sucursal_id, { numero: '', fecha: hoyBogota() }])));
  const cambiar = (id, valor) => setValores((actual) => ({ ...actual, [id]: valor }));
  const invalido = tiendas.some((t) => validarEnvio(valores[t.sucursal_id], rango) !== '');
  const varias = tiendas.length > 1;
  const confirmar = () => onConfirm(tiendas.map((t) => ({
    sucursal_id: t.sucursal_id,
    numero_pedido_proveedor: valores[t.sucursal_id].numero.trim(),
    fecha_envio: valores[t.sucursal_id].fecha,
  })));
  return (
    <DialogoPedido
      titulo={varias ? 'Marcar como enviados los pedidos seleccionados' : `Marcar como enviado el pedido de ${tiendas[0].nombre}`}
      textoConfirmar={plural(tiendas.length, 'Marcar como enviado', 'Marcar como enviados')}
      confirmarDeshabilitado={invalido} ancho="640px"
      descripcion={(
        <>
          <span>Anote el número de orden que HMCL le dio a cada pedido y la fecha en que se envió.</span>
          <span style={mutedStyle}>
            Una vez enviado, el pedido ya no se puede reabrir ni ajustar; sólo se puede corregir el número de orden.
          </span>
        </>
      )}
      ocupado={ocupado} error={error} onConfirm={confirmar} onCancel={onCancel}
    >
      {tiendas.map((t) => (
        <FilaEnvio key={t.sucursal_id} tienda={t} valor={valores[t.sucursal_id]} rango={rango} onCambio={(v) => cambiar(t.sucursal_id, v)} />
      ))}
    </DialogoPedido>
  );
}
