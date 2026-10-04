'use client';
/** Inline validation messages of an editor (nothing when there are none). */
import { errorStyle } from './styles';

export default function Mensajes({ mensajes }) {
  if (!mensajes.length) return null;
  return (
    <div role="alert" style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
      {mensajes.map((m) => <p key={m} style={errorStyle}>{m}</p>)}
    </div>
  );
}
