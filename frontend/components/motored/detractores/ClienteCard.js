/** Customer and motorcycle data of the case (`registro`). */
import InfoTooltip from '../InfoTooltip';
import { cardStyle, mutedStyle } from './styles';
import { formatFecha, whatsappUrl } from './labels';

const linkStyle = { color: 'var(--motored-primary, #e20714)', textDecoration: 'underline', fontWeight: 600 };
const SIC_HELP = 'Código con el que HMCL identifica el centro de servicio donde se atendió la moto.';

function Field({ label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', fontSize: '0.85rem' }}>
      <span style={{ fontSize: '0.7rem', ...mutedStyle }}>{label}</span>
      {children || '—'}
    </div>
  );
}

function Celular({ celular }) {
  if (!celular) return null;
  const wa = whatsappUrl(celular);
  return (
    <span style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
      <a href={`tel:${celular}`} style={linkStyle}>{celular}</a>
      {wa && <a href={wa} style={linkStyle} target="_blank" rel="noopener noreferrer">Escribir por WhatsApp</a>}
    </span>
  );
}

export default function ClienteCard({ registro }) {
  return (
    <section style={cardStyle}>
      <h2 className="motored-h-seccion">Cliente</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.75rem' }}>
        <Field label="Nombre">{registro.nombre}</Field>
        <Field label="Cédula">{registro.cedula}</Field>
        <Field label="Celular"><Celular celular={registro.celular} /></Field>
        <Field label="Placa">{registro.placa}</Field>
        <Field label="Línea">{registro.linea}</Field>
        <Field label={<>SIC <InfoTooltip text={SIC_HELP} /></>}>{registro.sic}</Field>
        <Field label="Centro de servicio">{registro.centro_servicio}</Field>
        <Field label="Carga">
          {registro.carga && `${registro.carga.nombre_archivo} (${formatFecha(registro.carga.fecha)})`}
        </Field>
      </div>
    </section>
  );
}
