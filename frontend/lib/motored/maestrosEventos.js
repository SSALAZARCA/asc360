/**
 * Motored -- "maestros changed" signal. A successful maestros write (form
 * save, deactivate/reactivate, bulk upload) announces it so the screens that
 * show derived data -- the health warnings in `MaestrosTabs` -- fetch it
 * again instead of waiting for a page reload.
 */

export const EVENTO_MAESTROS_CAMBIARON = 'motored:maestros-cambiaron';

export function avisarMaestrosCambiaron() {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new Event(EVENTO_MAESTROS_CAMBIARON));
}

/** Runs `alCambiar` on every announcement; returns the unsubscribe. */
export function escucharMaestrosCambiaron(alCambiar) {
  if (typeof window === 'undefined') return () => {};
  window.addEventListener(EVENTO_MAESTROS_CAMBIARON, alCambiar);
  return () => window.removeEventListener(EVENTO_MAESTROS_CAMBIARON, alCambiar);
}
