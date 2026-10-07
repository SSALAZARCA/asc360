'use client';
/**
 * frontend/components/motored/usuarios/CedulaUsuario.js
 *
 * The usuario's cédula in Gestión de usuarios
 * (odd/motored-reporte-diario-asesor, T1): its state (Aprobada / Pendiente
 * / Sin cédula), the row editor and the ADMIN actions. Saving from the
 * editor approves the cédula (the backend validates it against the active
 * vendedor master and against other approved usuarios). A cédula typed in
 * Lore stays Pendiente until "Aprobar cédula"; approving the registration
 * itself never approves it.
 */
import { useState } from 'react';
import InfoTooltip from '../InfoTooltip';
import MotoredIconAction from '../MotoredIconAction';
import {
  fijarCedulaUsuario, aprobarCedulaUsuario, rechazarCedulaUsuario,
  quitarCedulaUsuario,
} from '../../../lib/motored/api';

export const CEDULA_TOOLTIP = 'La cédula vincula al usuario con el maestro '
  + 'de Vendedores para enviarle su reporte diario por Lore. Solo se usa '
  + 'cuando está aprobada.';

const BADGE = {
  display: 'inline-block', padding: '2px 8px', fontSize: '0.7rem',
  fontWeight: 700, whiteSpace: 'nowrap',
  borderRadius: 'var(--motored-radius-pill, 999px)',
};
const ESTADOS = {
  aprobada: {
    texto: 'Aprobada',
    style: { background: 'var(--motored-success, #2e7d4f)', color: '#fff' },
  },
  pendiente: {
    texto: 'Pendiente',
    style: { background: 'var(--motored-warning, #b7791f)', color: '#fff' },
  },
  sin: {
    texto: 'Sin cédula',
    style: {
      background: 'transparent',
      color: 'var(--motored-text-muted, #5a5a5a)',
      border: '1px solid var(--motored-border, #e4e4e7)',
    },
  },
};
const MUTED = { color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.7rem' };
const INPUT = { width: '9rem', fontSize: '13px' };

export function estadoCedula(u) {
  if (!u.cedula) return 'sin';
  return u.cedula_aprobada ? 'aprobada' : 'pendiente';
}

export function CedulaHeader() {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
      Cédula <InfoTooltip text={CEDULA_TOOLTIP} />
    </span>
  );
}

function CedulaEstado({ usuario }) {
  const estado = ESTADOS[estadoCedula(usuario)];
  const fuera = usuario.cedula && usuario.cedula_en_maestro === false;
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', gap: '2px' }}>
      <span style={{ display: 'inline-flex', gap: '6px', alignItems: 'center' }}>
        {usuario.cedula && <span>{usuario.cedula}</span>}
        <span style={{ ...BADGE, ...estado.style }}>{estado.texto}</span>
      </span>
      {fuera && <span style={MUTED}>No está en el maestro de Vendedores</span>}
    </span>
  );
}

function CedulaEditor({ usuario, onGuardar, onCancelar }) {
  const [valor, setValor] = useState(usuario.cedula || '');
  const guardar = async () => {
    if (await onGuardar(usuario.id, valor)) onCancelar();
  };
  return (
    <span style={{ display: 'inline-flex', gap: '4px', alignItems: 'center' }}>
      <input
        aria-label={`Cédula de ${usuario.nombre}`} inputMode="numeric"
        style={INPUT} value={valor} onChange={(e) => setValor(e.target.value)}
      />
      <MotoredIconAction action="Guardar" label="Guardar cédula" onClick={guardar} />
      <MotoredIconAction action="Cancelar" label="Cancelar edición" onClick={onCancelar} />
    </span>
  );
}

function confirmar(texto, accion) {
  if (window.confirm(texto)) accion();
}

function CedulaAcciones({ usuario, acciones, onEditar }) {
  const estado = estadoCedula(usuario);
  const { aprobar, rechazar, quitar } = acciones;
  return (
    <>
      <MotoredIconAction
        action="Editar" label={estado === 'sin' ? 'Agregar cédula' : 'Editar cédula'}
        onClick={onEditar}
      />
      {estado === 'pendiente' && (
        <>
          <MotoredIconAction
            action="Aprobar" label="Aprobar cédula"
            onClick={() => aprobar(usuario.id)}
          />
          <MotoredIconAction
            action="Rechazar" label="Rechazar cédula"
            onClick={() => confirmar(
              `¿Rechazar la cédula de "${usuario.nombre}"? Se borra.`,
              () => rechazar(usuario.id),
            )}
          />
        </>
      )}
      {estado === 'aprobada' && (
        <MotoredIconAction
          action="Rechazar" label="Quitar cédula"
          onClick={() => confirmar(
            `¿Quitar la cédula de "${usuario.nombre}"? `
              + 'Dejará de recibir su reporte diario.',
            () => quitar(usuario.id),
          )}
        />
      )}
    </>
  );
}

/** Table cell: state + actions, or the inline editor while editing. */
export function CedulaCelda({ usuario, acciones }) {
  const [editando, setEditando] = useState(false);
  if (editando) {
    return (
      <CedulaEditor
        usuario={usuario} onGuardar={acciones.fijar}
        onCancelar={() => setEditando(false)}
      />
    );
  }
  return (
    <span style={{ display: 'inline-flex', gap: '4px', alignItems: 'center', flexWrap: 'wrap' }}>
      <CedulaEstado usuario={usuario} />
      <CedulaAcciones usuario={usuario} acciones={acciones} onEditar={() => setEditando(true)} />
    </span>
  );
}

/** ADMIN cédula actions; `onCambio` reloads the lists afterwards. */
export function useCedulaAcciones(onCambio) {
  const [error, setError] = useState('');
  const ejecutar = async (llamada, fallback) => {
    setError('');
    try {
      await llamada();
      await onCambio();
      return true;
    } catch (err) {
      setError(err.message || fallback);
      return false;
    }
  };
  return {
    error,
    fijar: (id, cedula) => ejecutar(
      () => fijarCedulaUsuario(id, cedula), 'Error al guardar la cédula'),
    aprobar: (id) => ejecutar(
      () => aprobarCedulaUsuario(id), 'Error al aprobar la cédula'),
    rechazar: (id) => ejecutar(
      () => rechazarCedulaUsuario(id), 'Error al rechazar la cédula'),
    quitar: (id) => ejecutar(
      () => quitarCedulaUsuario(id), 'Error al quitar la cédula'),
  };
}
