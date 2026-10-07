'use client';
/**
 * frontend/components/motored/usuarios/EnlaceInforme.js
 *
 * The asesor's personal report link in Gestión de usuarios
 * (odd/motored-reporte-diario-asesor, T3a): its state ("Activo · último
 * acceso ..." or "Sin enlace") and the ADMIN actions. "Generar enlace
 * nuevo" cancels the previous link and Lore sends the new one; "Anular
 * enlace" cancels it. Both ask for confirmation. The backend never returns
 * the token or the URL, so this screen never shows them.
 *
 * A link needs an active, approved usuario with an approved cédula and a
 * linked Telegram; otherwise the actions are disabled with the reason and
 * no request is made for that row.
 */
import { useCallback, useEffect, useState } from 'react';
import InfoTooltip from '../InfoTooltip';
import MotoredIconAction from '../MotoredIconAction';
import { fechaHoraBogota } from '../../../lib/motored/fechas';
import {
  obtenerEnlaceInforme, generarEnlaceInforme, anularEnlaceInforme,
} from '../../../lib/motored/api';

export const ENLACE_TOOLTIP = 'Enlace secreto y permanente que Lore le '
  + 'envía al asesor para ver su informe. Al abrirlo debe escribir su '
  + 'cédula. Generar uno nuevo anula el anterior.';

const MUTED = { color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.7rem' };
const ERROR = { color: 'var(--motored-danger, #c0392b)', fontSize: '0.7rem' };
const SIN_ENLACE = { activo: false, creado_en: null, ultimo_acceso_en: null };

/** Why the usuario cannot hold a link, or null when it can. */
export function impedimentoEnlace(u) {
  if (!u.activo) return 'Usuario inactivo';
  if ((u.status || 'approved') !== 'approved') return 'Registro sin aprobar';
  if (!u.cedula || !u.cedula_aprobada) return 'Necesita cédula aprobada';
  if (!u.telegram_vinculado) return 'Necesita Telegram vinculado';
  return null;
}

export function textoEstadoEnlace(estado) {
  if (!estado || !estado.activo) return 'Sin enlace';
  const acceso = estado.ultimo_acceso_en
    ? fechaHoraBogota(estado.ultimo_acceso_en) : 'nunca';
  return `Activo · último acceso ${acceso}`;
}

export function EnlaceInformeHeader() {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
      Enlace del informe <InfoTooltip text={ENLACE_TOOLTIP} />
    </span>
  );
}

function useEnlace(usuarioId, elegible) {
  const [estado, setEstado] = useState(SIN_ENLACE);
  const [error, setError] = useState('');
  useEffect(() => {
    let vigente = true;
    setEstado(SIN_ENLACE);
    if (!elegible) return undefined;
    (async () => {
      try {
        const actual = await obtenerEnlaceInforme(usuarioId);
        if (vigente && actual) setEstado(actual);
      } catch (err) {
        if (vigente) setError(err.message || 'Error al leer el enlace');
      }
    })();
    return () => { vigente = false; };
  }, [usuarioId, elegible]);
  const ejecutar = useCallback(async (llamada, fallback) => {
    setError('');
    try {
      setEstado(await llamada(usuarioId));
    } catch (err) {
      setError(err.message || fallback);
    }
  }, [usuarioId]);
  return { estado, error, ejecutar };
}

/** Table cell: link state, actions, and the reason they are disabled. */
export function EnlaceInformeCelda({ usuario }) {
  const impedimento = impedimentoEnlace(usuario);
  const { estado, error, ejecutar } = useEnlace(usuario.id, !impedimento);
  const generar = () => {
    if (!window.confirm(
      `¿Generar un enlace nuevo para "${usuario.nombre}"? Se anula el `
        + 'enlace anterior y Lore le envía el nuevo.',
    )) return;
    ejecutar(generarEnlaceInforme, 'Error al generar el enlace');
  };
  const anular = () => {
    if (!window.confirm(
      `¿Anular el enlace del informe de "${usuario.nombre}"? `
        + 'Dejará de funcionar de inmediato.',
    )) return;
    ejecutar(anularEnlaceInforme, 'Error al anular el enlace');
  };
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', gap: '2px' }}>
      <span style={{ display: 'inline-flex', gap: '4px', alignItems: 'center', flexWrap: 'wrap' }}>
        <span>{textoEstadoEnlace(estado)}</span>
        <MotoredIconAction
          action="Vincular Telegram" label="Generar enlace nuevo"
          onClick={generar} disabled={Boolean(impedimento)}
        />
        {estado.activo && (
          <MotoredIconAction
            action="Anular" label="Anular enlace" onClick={anular}
          />
        )}
      </span>
      {impedimento && <span style={MUTED}>{impedimento}</span>}
      {error && <span role="alert" style={ERROR}>{error}</span>}
    </span>
  );
}
