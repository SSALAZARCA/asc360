/** Default range of the survey results download: the current month in Bogota time (UTC-5, no DST). */
const BOGOTA_MS = -5 * 60 * 60 * 1000;

const dosDigitos = (n) => String(n).padStart(2, '0');

export function rangoMesActual(ahora = new Date()) {
  const local = new Date(ahora.getTime() + BOGOTA_MS);
  const anio = local.getUTCFullYear();
  const mes = local.getUTCMonth();
  const ultimo = new Date(Date.UTC(anio, mes + 1, 0)).getUTCDate();
  const prefijo = `${anio}-${dosDigitos(mes + 1)}`;
  return { desde: `${prefijo}-01`, hasta: `${prefijo}-${dosDigitos(ultimo)}` };
}
