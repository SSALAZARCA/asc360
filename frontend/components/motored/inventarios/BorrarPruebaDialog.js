'use client';
/**
 * ADMIN confirms the hard delete of a TEST conteo (odd/tasks/motored-conteo-prueba.md):
 * the conteo and everything recorded in it (pairs, readings, reconteos, result) are gone.
 */
import { useState } from 'react';
import DialogoPedido from '../pedidos/DialogoPedido';
import { borrarConteoPrueba } from '../../../lib/motored/conteosApi';

export default function BorrarPruebaDialog({ conteo, onCancel, onListo }) {
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState('');

  const confirmar = async () => {
    setOcupado(true);
    setError('');
    try {
      await borrarConteoPrueba(conteo.id);
      onListo();
    } catch (err) {
      setError(err.message || 'No se pudo borrar el conteo de prueba.');
      setOcupado(false);
    }
  };

  return (
    <DialogoPedido
      titulo={`Borrar conteo de prueba · ${conteo.sucursal.nombre}`}
      descripcion={(
        <span>
          Se borran para siempre el conteo y todo lo que se registró en él: parejas, lecturas, reconteos y resultado.
          Las ubicaciones de la tienda se conservan. Esta acción no se puede deshacer.
        </span>
      )}
      error={error} ocupado={ocupado}
      textoConfirmar="Borrar conteo de prueba" onConfirm={confirmar} onCancel={onCancel}
    />
  );
}
