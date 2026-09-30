'use client';
/**
 * frontend/app/motored/usuarios/page.js
 *
 * ADMIN-only usuario list/create/deactivate (sdd/motored-pedidos-cimientos,
 * Phase 6, task 6.2). Backend already enforces ADMIN-only server-side
 * (`backend/app/motored/api/usuarios.py`'s `_require_admin`) -- this screen
 * additionally hides itself from the menu for non-ADMIN roles
 * (`MotoredSidebar`'s `adminOnly` filter) and redirects a non-ADMIN who
 * navigates here directly straight back to `/motored/maestros`, mirroring
 * asc360's `admin-layout.js` division of labor (UI convenience gate, real
 * enforcement is server-side).
 *
 * odd/motored-salir-y-cambio-password adds a "Cambiar contraseña" action on
 * every row with web access (email and not `ASESOR_MOSTRADOR`): the ADMIN
 * sets a new password through `CambiarPasswordForm`.
 *
 * sdd/motored-ventas-perdidas-bot, Phase 4 "Approval service + Usuarios UI"
 * (design D5) adds two things to this same screen (not a new route):
 * - A "Solicitudes pendientes" section (`status='pending'` advisors from
 *   the bot's self-registration flow) with Aprobar/Rechazar actions --
 *   both call the backend's `resolver_solicitud` via
 *   `aprobarUsuario`/`rechazarUsuario`.
 * - A "Vincular Telegram" / "Desvincular Telegram" action on the
 *   authenticated ADMIN's OWN row only (matched by id against the
 *   `motored_user` session, never a different user's row -- design D5: an
 *   ADMIN links only their own `telegram_id`). Vincular shows a one-time
 *   code (`generarCodigoTelegram`) to type into the Lore bot.
 */
import MotoredTableScroll from '../../../components/motored/MotoredTableScroll';
import MotoredIconAction from '../../../components/motored/MotoredIconAction';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import MotoredLayout from '../motored-layout';
import CambiarPasswordForm from '../../../components/motored/CambiarPasswordForm';
import {
  listUsuarios, createUsuario, deactivateUsuario, reactivateUsuario,
  listSolicitudesPendientes, aprobarUsuario, rechazarUsuario,
  generarCodigoTelegram, desvincularTelegram, resetPasswordUsuario,
} from '../../../lib/motored/api';
import { MOTORED_USER_KEY } from '../../../lib/motored/motoredFetch';

const ROLES = ['ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA', 'SERVICIO_CLIENTE'];
const ROLE_LABELS = { SERVICIO_CLIENTE: 'Servicio al cliente' };
const emptyForm = { nombre: '', email: '', password: '', role: 'CONSULTA' };

function UsuarioForm({ form, setForm, onSubmit }) {
  return (
    <form onSubmit={onSubmit} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Nombre
        <input value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} required />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Email
        <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Password
        <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Rol
        <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          {ROLES.map((r) => (
            <option key={r} value={r} style={{ color: '#1a1a18' }}>
              {ROLE_LABELS[r] || r}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" className="motored-btn motored-btn-primary">Crear usuario</button>
    </form>
  );
}

function tieneAccesoWeb(u) {
  return Boolean(u.email) && u.role !== 'ASESOR_MOSTRADOR';
}

function UsuariosTable({ usuarios, onDeactivate, onReactivate, ownUserId, onVincularTelegram, onDesvincularTelegram, onCambiarPassword }) {
  const handleDeactivateClick = (u) => {
    if (window.confirm(`¿Desactivar a "${u.nombre}"? No se elimina, queda marcado como inactivo.`)) {
      onDeactivate(u.id);
    }
  };
  const handleReactivateClick = (u) => {
    if (window.confirm(`¿Reactivar a "${u.nombre}"? Queda marcado como activo; su estado de aprobación no cambia.`)) {
      onReactivate(u.id);
    }
  };

  return (
    <MotoredTableScroll>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
            <th style={{ padding: '0 12px 8px 0' }}>Nombre</th>
            <th style={{ padding: '0 12px 8px 0' }}>Email</th>
            <th style={{ padding: '0 12px 8px 0' }}>Rol</th>
            <th style={{ padding: '0 12px 8px 0' }}>Estado</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {usuarios.map((u) => (
            <tr key={u.id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
              <td style={{ padding: '10px 12px 10px 0' }}>{u.nombre}</td>
              <td style={{ padding: '10px 12px 10px 0' }}>{u.email}</td>
              <td style={{ padding: '10px 12px 10px 0' }}>{u.role}</td>
              <td style={{ padding: '10px 12px 10px 0' }}>{u.activo ? 'Activo' : 'Inactivo'}</td>
              <td style={{ padding: '10px 0', display: 'flex', gap: '0.5rem' }}>
                {/* Nunca un botón rojo dentro de una tabla -- ver
                SucursalesTab.js para la misma regla aplicada. */}
                {u.activo ? (
                  <MotoredIconAction action="Desactivar" onClick={() => handleDeactivateClick(u)} />
                ) : (
                  <MotoredIconAction action="Reactivar" onClick={() => handleReactivateClick(u)} />
                )}
                {tieneAccesoWeb(u) && (
                  <MotoredIconAction action="Cambiar contraseña" onClick={() => onCambiarPassword(u)} />
                )}
                {/* Vincular/Desvincular Telegram SOLO en la propia fila del
                ADMIN autenticado (sdd/motored-ventas-perdidas-bot, design D5:
                "ADMIN telegram-linking independent of role") -- nunca sobre
                la fila de otro usuario. */}
                {u.id === ownUserId && (
                  u.telegram_vinculado ? (
                    <MotoredIconAction action="Desvincular Telegram" onClick={() => onDesvincularTelegram(u.id)} />
                  ) : (
                    <MotoredIconAction action="Vincular Telegram" onClick={() => onVincularTelegram(u.id)} />
                  )
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}

function SolicitudesPendientesTable({ solicitudes, onAprobar, onRechazar }) {
  if (solicitudes.length === 0) {
    return <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>No hay solicitudes pendientes.</p>;
  }

  return (
    <MotoredTableScroll>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
            <th style={{ padding: '0 12px 8px 0' }}>Nombre</th>
            <th style={{ padding: '0 12px 8px 0' }}>Teléfono</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {solicitudes.map((s) => (
            <tr key={s.id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
              <td style={{ padding: '10px 12px 10px 0' }}>{s.nombre}</td>
              <td style={{ padding: '10px 12px 10px 0' }}>{s.phone}</td>
              <td style={{ padding: '10px 0', display: 'flex', gap: '0.5rem' }}>
                <MotoredIconAction action="Aprobar" onClick={() => onAprobar(s.id)} />
                <MotoredIconAction action="Rechazar" onClick={() => onRechazar(s.id)} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}

function useAdminGate() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);
  const [ownUserId, setOwnUserId] = useState(null);

  useEffect(() => {
    const stored = sessionStorage.getItem(MOTORED_USER_KEY);
    let parsed = null;
    try {
      parsed = stored ? JSON.parse(stored) : null;
    } catch {
      parsed = null;
    }
    if (parsed?.role !== 'ADMIN') {
      router.push('/motored/maestros');
      return;
    }
    setOwnUserId(parsed.id ?? null);
    setAllowed(true);
  }, [router]);

  return { allowed, ownUserId };
}

function useSolicitudesPendientes(enabled) {
  const [solicitudes, setSolicitudes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await listSolicitudesPendientes();
      setSolicitudes(data);
    } catch (err) {
      setError(err.message || 'Error al cargar solicitudes pendientes');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (enabled) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  const aprobar = async (id) => {
    setError('');
    try {
      await aprobarUsuario(id);
      await load();
    } catch (err) {
      setError(err.message || 'Error al aprobar la solicitud');
    }
  };

  const rechazar = async (id) => {
    setError('');
    try {
      await rechazarUsuario(id);
      await load();
    } catch (err) {
      setError(err.message || 'Error al rechazar la solicitud');
    }
  };

  return { solicitudes, loading, error, aprobar, rechazar };
}

function useTelegramVinculacion(onDesvinculado) {
  /**
   * Post-Phase-4 review (finding #7): the callback ONLY ever fires from
   * `desvincular` -- renamed from the previous `onLinked` (wired as
   * `useTelegramVinculacion(reload)`), which misleadingly suggested it
   * also fired after a successful `vincular`. Judgment call: it does NOT
   * -- `vincular` only generates and displays a one-time code; the row's
   * `telegram_vinculado` flag doesn't flip to `true` until the Lore bot
   * itself consumes that code server-side (Fase 5), which never happens
   * synchronously with this click. Reloading the usuarios list right
   * after generating a code would therefore be a pointless extra request
   * that changes nothing on screen. `desvincular`, by contrast, DOES
   * change `telegram_vinculado` immediately, so its reload is genuinely
   * needed.
   */
  const [codigo, setCodigo] = useState(null);
  const [error, setError] = useState('');

  const vincular = async () => {
    setError('');
    setCodigo(null);
    try {
      const data = await generarCodigoTelegram();
      setCodigo(data);
    } catch (err) {
      setError(err.message || 'Error al generar el código de vinculación');
    }
  };

  const desvincular = async () => {
    setError('');
    try {
      await desvincularTelegram();
      setCodigo(null);
      await onDesvinculado();
    } catch (err) {
      setError(err.message || 'Error al desvincular Telegram');
    }
  };

  return { codigo, error, vincular, desvincular };
}

function usePasswordReset() {
  /** `objetivo` es el usuario cuyo formulario está abierto; `exito` el
   * aviso posterior. Nunca guarda la contraseña: solo la pasa a la API. */
  const [objetivo, setObjetivo] = useState(null);
  const [error, setError] = useState('');
  const [exito, setExito] = useState('');

  const abrir = (usuario) => {
    setObjetivo(usuario);
    setError('');
    setExito('');
  };

  const cerrar = () => {
    setObjetivo(null);
    setError('');
  };

  const guardar = async (password) => {
    setError('');
    try {
      await resetPasswordUsuario(objetivo.id, password);
      setExito(`Contraseña actualizada para ${objetivo.nombre}`);
      setObjetivo(null);
    } catch (err) {
      setError(err.message || 'Error al cambiar la contraseña');
    }
  };

  return { objetivo, error, exito, abrir, cerrar, guardar };
}

function useUsuarios(enabled) {
  const [usuarios, setUsuarios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await listUsuarios();
      setUsuarios(data);
    } catch (err) {
      setError(err.message || 'Error al cargar usuarios');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (enabled) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  const create = async (form) => {
    setError('');
    try {
      await createUsuario(form);
      await load();
      return true;
    } catch (err) {
      setError(err.message || 'Error al crear usuario');
      return false;
    }
  };

  const deactivate = async (id) => {
    setError('');
    try {
      await deactivateUsuario(id);
      await load();
    } catch (err) {
      setError(err.message || 'Error al desactivar usuario');
    }
  };

  const reactivate = async (id) => {
    setError('');
    try {
      await reactivateUsuario(id);
      await load();
    } catch (err) {
      setError(err.message || 'Error al reactivar usuario');
    }
  };

  return { usuarios, loading, error, create, deactivate, reactivate, reload: load };
}

/**
 * Post-Phase-4 review (finding #6): wraps the one-time Telegram-code
 * banner + its own error message -- previously inlined straight into
 * `UsuariosContent`, one of the 4 concerns that function was mixing.
 * Single purpose: show the OUTCOME of a `vincular`/`desvincular` action,
 * nothing else (the row-level buttons that TRIGGER those actions still
 * live in `UsuariosTable`, since they're rendered per-row, not here).
 */
function TelegramLinkPanel({ codigo, error }) {
  return (
    <>
      {error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>}
      {codigo && (
        <p style={{ fontSize: '0.85rem' }}>
          Código de vinculación: <strong>{codigo.codigo}</strong> (válido hasta {codigo.expira_en}). Escribilo en el bot Lore para vincular tu Telegram.
        </p>
      )}
    </>
  );
}

/**
 * Post-Phase-4 review (finding #6): wraps the "Solicitudes pendientes"
 * heading + loading/error state + `SolicitudesPendientesTable` -- another
 * of the 4 concerns `UsuariosContent` was mixing. Single purpose: render
 * the pending-requests section end-to-end.
 */
function SolicitudesPendientesPanel({ solicitudes, loading, error, onAprobar, onRechazar }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <h3 className="motored-h-seccion">Solicitudes pendientes</h3>
      {error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>}
      {loading ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando...</p>
      ) : (
        <SolicitudesPendientesTable solicitudes={solicitudes} onAprobar={onAprobar} onRechazar={onRechazar} />
      )}
    </div>
  );
}

/** Aviso de éxito + formulario "Cambiar contraseña" (uno a la vez). */
function PasswordResetPanel({ state }) {
  return (
    <>
      {state.exito && <p style={{ color: 'var(--motored-text, #1a1a18)', fontSize: '0.8rem' }}>{state.exito}</p>}
      {state.objetivo && (
        <CambiarPasswordForm
          key={state.objetivo.id}
          usuario={state.objetivo}
          onSubmit={state.guardar}
          onCancel={state.cerrar}
          serverError={state.error}
        />
      )}
    </>
  );
}

function UsuariosContent() {
  /**
   * Post-Phase-4 review (finding #6): this function used to mix 4
   * unrelated concerns inline (create-usuario form, main usuarios table +
   * own-row Telegram link/unlink, one-time Telegram code banner,
   * pending-solicitudes section). Pure decomposition, no behavior
   * change: `TelegramLinkPanel` and `SolicitudesPendientesPanel` now own
   * their own rendering; this function is left composing them plus the
   * create-usuario form and the main table.
   */
  const { allowed, ownUserId } = useAdminGate();
  const { usuarios, loading, error, create, deactivate, reactivate, reload } = useUsuarios(allowed);
  const solicitudesState = useSolicitudesPendientes(allowed);
  const telegramState = useTelegramVinculacion(reload);
  const passwordState = usePasswordReset();
  const [form, setForm] = useState(emptyForm);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const ok = await create(form);
    if (ok) setForm(emptyForm);
  };

  if (!allowed) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <h2 className="motored-h-seccion">Usuarios</h2>

      {error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>}

      <UsuarioForm form={form} setForm={setForm} onSubmit={handleSubmit} />

      {loading ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando...</p>
      ) : (
        <UsuariosTable
          usuarios={usuarios}
          onDeactivate={deactivate}
          onReactivate={reactivate}
          ownUserId={ownUserId}
          onVincularTelegram={telegramState.vincular}
          onDesvincularTelegram={telegramState.desvincular}
          onCambiarPassword={passwordState.abrir}
        />
      )}

      <PasswordResetPanel state={passwordState} />

      <TelegramLinkPanel codigo={telegramState.codigo} error={telegramState.error} />

      <SolicitudesPendientesPanel
        solicitudes={solicitudesState.solicitudes}
        loading={solicitudesState.loading}
        error={solicitudesState.error}
        onAprobar={solicitudesState.aprobar}
        onRechazar={solicitudesState.rechazar}
      />
    </div>
  );
}

export default function UsuariosPage() {
  return (
    <MotoredLayout>
      <UsuariosContent />
    </MotoredLayout>
  );
}
