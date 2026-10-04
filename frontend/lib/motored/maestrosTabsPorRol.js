/**
 * frontend/lib/motored/maestrosTabsPorRol.js
 *
 * Which Maestros tabs a role may see. A tab with `roles` is visible only to
 * those roles (Presupuestos: ADMIN and GERENCIA). A tab without `roles` is a
 * regular tab: everybody sees it EXCEPT GERENCIA, which is confined to the
 * budgets. The backend is the real enforcement; this keeps the UI from
 * offering screens that would answer 403.
 */
import { ROLE_GERENCIA } from './session';

/** Roles that see the Presupuestos tab (the page and the permission matrix share it). */
export const PRESUPUESTOS_ROLES = ['ADMIN', 'GERENCIA'];

export function filtrarTabsPorRol(tabs, rol) {
  return tabs.filter((tab) => (tab.roles ? tab.roles.includes(rol) : rol !== ROLE_GERENCIA));
}
