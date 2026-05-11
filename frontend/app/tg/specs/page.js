'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { authFetch } from '../../../lib/authFetch';
import TgNav from '../../../components/tg/TgNav';

const SECTIONS = [
  {
    label: 'Motor',
    fields: [
      { key: 'cilindrada',        label: 'Cilindrada' },
      { key: 'potencia',          label: 'Potencia' },
      { key: 'relacion_compresion', label: 'Relación de compresión' },
      { key: 'combustible',       label: 'Sistema de combustible' },
      { key: 'vueltas_aire',      label: 'Tornillo de aire' },
      { key: 'posicion_cortina',  label: 'Posición cortina' },
      { key: 'sistemas_control',  label: 'Sistemas de control' },
    ],
  },
  {
    label: 'Dimensiones y peso',
    fields: [
      { key: 'largo_total',    label: 'Largo total' },
      { key: 'ancho_total',    label: 'Ancho total' },
      { key: 'altura_total',   label: 'Altura total' },
      { key: 'altura_silla',   label: 'Altura de silla' },
      { key: 'distancia_suelo', label: 'Distancia al suelo' },
      { key: 'distancia_ejes', label: 'Distancia entre ejes' },
      { key: 'peso',           label: 'Peso' },
    ],
  },
  {
    label: 'Combustible y llantas',
    fields: [
      { key: 'tanque_combustible', label: 'Tanque de combustible' },
      { key: 'llanta_delantera',   label: 'Llanta delantera' },
      { key: 'llanta_trasera',     label: 'Llanta trasera' },
    ],
  },
];

export default function TgSpecs() {
  const router = useRouter();
  const [user, setUser]         = useState(null);
  const [models, setModels]     = useState([]);
  const [selected, setSelected] = useState('');
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);

  useEffect(() => {
    const stored = sessionStorage.getItem('um_user');
    const token  = sessionStorage.getItem('um_token');
    if (!stored || !token) { router.replace('/tg'); return; }
    setUser(JSON.parse(stored));
    fetchModels();
  }, []);

  const fetchModels = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch('/vehicle-models');
      if (res.status === 401) { router.replace('/tg'); return; }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setModels(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(`No se pudo cargar la lista de modelos: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const current = models.find(m => m.modelo === selected) ?? null;

  return (
    <div style={{ minHeight: '100dvh', background: '#0a0a0c', paddingBottom: '5.5rem' }}>

      {/* Header */}
      <div style={{ background: '#13131a', borderBottom: '1px solid rgba(255,255,255,0.06)', padding: '0.9rem 1.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem', position: 'sticky', top: 0, zIndex: 10 }}>
        <img src="/logo.png" alt="UM" style={{ height: 28, objectFit: 'contain', opacity: 0.9, flexShrink: 0 }} />
        <div>
          <p style={{ margin: 0, fontWeight: 800, fontSize: '0.85rem', color: '#fff' }}>Especificaciones técnicas</p>
          <p style={{ margin: 0, fontSize: '0.6rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.07em' }}>Modelos UM</p>
        </div>
      </div>

      <div style={{ padding: '1rem 0.75rem 0' }}>

        {/* Selector de modelo */}
        <div style={{ background: '#13131a', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 12, padding: '0.75rem 1rem', marginBottom: '1rem' }}>
          <p style={{ margin: '0 0 0.5rem', fontSize: '0.58rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 700 }}>
            Seleccioná el modelo
          </p>
          {loading ? (
            <p style={{ margin: 0, fontSize: '0.75rem', color: '#3f3f55' }}>Cargando modelos...</p>
          ) : error ? (
            <p style={{ margin: 0, fontSize: '0.72rem', color: '#ef4444' }}>{error}</p>
          ) : (
            <select
              value={selected}
              onChange={e => setSelected(e.target.value)}
              style={{
                width: '100%',
                background: '#0a0a0c',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 8,
                color: selected ? '#fff' : '#606075',
                fontSize: '0.82rem',
                fontWeight: 700,
                padding: '0.6rem 0.75rem',
                outline: 'none',
                appearance: 'none',
                WebkitAppearance: 'none',
                cursor: 'pointer',
              }}
            >
              <option value="">— Elegí un modelo —</option>
              {models.map(m => (
                <option key={m.id} value={m.modelo}>{m.modelo}</option>
              ))}
            </select>
          )}
        </div>

        {/* Ficha técnica */}
        {current && (
          <>
            {/* Badge del modelo */}
            <div style={{ background: 'rgba(255,95,51,0.08)', border: '1px solid rgba(255,95,51,0.25)', borderRadius: 12, padding: '0.75rem 1rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <p style={{ margin: 0, fontSize: '1rem', fontWeight: 900, color: '#ff8c5a', letterSpacing: '0.03em' }}>{current.modelo}</p>
                <p style={{ margin: '2px 0 0', fontSize: '0.6rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.07em' }}>{current.marca}</p>
              </div>
              <div style={{ background: 'rgba(255,95,51,0.12)', borderRadius: 8, padding: '0.3rem 0.65rem' }}>
                <p style={{ margin: 0, fontSize: '0.6rem', fontWeight: 800, color: '#ff5f33', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Ficha técnica</p>
              </div>
            </div>

            {/* Secciones */}
            {SECTIONS.map(section => {
              const rows = section.fields.filter(f => current[f.key]);
              if (rows.length === 0) return null;
              return (
                <div key={section.label} style={{ background: '#13131a', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 12, marginBottom: '0.75rem', overflow: 'hidden' }}>
                  <div style={{ padding: '0.6rem 1rem', borderBottom: '1px solid rgba(255,255,255,0.05)', background: 'rgba(255,255,255,0.02)' }}>
                    <p style={{ margin: 0, fontSize: '0.58rem', fontWeight: 800, color: '#ff5f33', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{section.label}</p>
                  </div>
                  {rows.map((f, i) => (
                    <div
                      key={f.key}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '0.65rem 1rem',
                        borderBottom: i < rows.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none',
                        gap: '0.75rem',
                      }}
                    >
                      <p style={{ margin: 0, fontSize: '0.7rem', color: '#606075', flexShrink: 0 }}>{f.label}</p>
                      <p style={{ margin: 0, fontSize: '0.75rem', fontWeight: 700, color: '#e2e2f0', textAlign: 'right', wordBreak: 'break-word' }}>{current[f.key]}</p>
                    </div>
                  ))}
                </div>
              );
            })}
          </>
        )}

        {/* Estado vacío */}
        {!loading && !error && !selected && (
          <div style={{ textAlign: 'center', padding: '3rem 1rem', color: '#3f3f55' }}>
            <p style={{ fontSize: '2rem', margin: '0 0 0.75rem' }}>🏍</p>
            <p style={{ margin: 0, fontSize: '0.75rem', fontWeight: 700, color: '#3f3f55' }}>Seleccioná un modelo para ver sus especificaciones</p>
          </div>
        )}
      </div>

      <TgNav userRole={user?.role} />
    </div>
  );
}
