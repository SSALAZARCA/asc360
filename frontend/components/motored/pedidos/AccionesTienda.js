'use client';
/** The lifecycle icons of ONE tienda (Cerrar, Reabrir, Exportar, Marcar como enviado, Corregir número), from what the backend allows. */
import MotoredIconAction from '../MotoredIconAction';
import { accionesVisibles } from './acciones';

export default function AccionesTienda({ tienda, alAccionar, ocupado = false, touch = true }) {
  const lista = accionesVisibles(tienda.acciones, tienda.unidades_a_pedir);
  return (
    <>
      {lista.map((a) => (
        <MotoredIconAction
          key={a.clave} action={a.accion} touch={touch} disabled={a.deshabilitada || ocupado}
          label={a.deshabilitada ? `${a.accion}: ${a.motivo}` : undefined}
          onClick={() => alAccionar(a.clave, tienda)}
        />
      ))}
    </>
  );
}
