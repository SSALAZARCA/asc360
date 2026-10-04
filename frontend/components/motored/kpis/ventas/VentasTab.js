/** Ventas tab (the full layout arrives in the next commit). */
export default function VentasTab({ data }) {
  return <section aria-label="Ventas" data-meses={data.meses.join(',')} />;
}
