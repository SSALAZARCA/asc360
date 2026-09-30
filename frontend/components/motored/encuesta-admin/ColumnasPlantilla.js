'use client';
/** Explains the template columns; non-obvious ones (SIC) get a tooltip. */
import InfoTooltip from '../InfoTooltip';

const COLUMNS = [
  { name: 'Nombre', help: 'Nombre del cliente. Obligatorio.' },
  { name: 'Cédula', help: 'Cédula de la persona a cuyo nombre está registrada la moto. Obligatoria.' },
  { name: 'Celular', help: 'Opcional.' },
  { name: 'Línea', help: 'Modelo de la moto. Opcional.' },
  { name: 'Placa', help: 'Obligatoria.' },
  {
    name: 'SIC', help: 'Opcional.',
    tooltip: 'Código con el que HMCL identifica el centro de servicio donde se atendió la moto.',
  },
  { name: 'Centro de servicio', help: 'Taller donde se atendió la moto. Opcional.' },
  { name: 'Tipo', help: 'Servicio taller o Venta. Obligatorio. Por ahora solo se encuestan los de Servicio taller.' },
];

export default function ColumnasPlantilla() {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <h3 className="motored-h-seccion">Columnas de la plantilla</h3>
      <ul style={{ margin: 0, paddingLeft: '1.1rem', fontSize: '0.8rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        {COLUMNS.map((c) => (
          <li key={c.name}>
            <strong>{c.name}</strong>
            {c.tooltip && <> <InfoTooltip text={c.tooltip} /></>}
            {' '}— {c.help}
          </li>
        ))}
      </ul>
    </section>
  );
}
