'use client';
import { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../../lib/authFetch';
import { FileUp, Download, RefreshCw, Search, CheckCircle, Clock, Bike, X, AlertCircle, Pencil, Send, FileText } from 'lucide-react';

function API() {
  return (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace(/^http://(?!localhost)/, 'https://');
}

// ---------------------------------------------------------------------------
// Badge de empadronamiento
// ---------------------------------------------------------------------------
function CertBadge({ generated }) {
  if (generated) {
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: '4px',
        fontSize: '9px', fontWeight: 700, letterSpacing: '0.05em',
        padding: '2px 8px', borderRadius: '20px',
        background: 'rgba(34,197,94,0.1)', color: '#22c55e',
        border: '1px solid rgba(34,197,94,0.25)', whiteSpace: 'nowrap',
      }}>
        <CheckCircle size={9} /> EMPADRONADO
      </span>
    );
  }
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      fontSize: '9px', fontWeight: 700, letterSpacing: '0.05em',
      padding: '2px 8px', borderRadius: '20px',
      background: 'rgba(96,96,117,0.15)', color: '#606075',
      border: '1px solid rgba(96,96,117,0.25)', whiteSpace: 'nowrap',
    }}>
      <Clock size={9} /> PENDIENTE
    </span>
  );
}

// ---------------------------------------------------------------------------
// Modal inline para carga de DIM
// ---------------------------------------------------------------------------
function DimUploadModal({ onUpload, onClose, uploading, result }) {
  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    onUpload(file);
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#13131a', border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '16px', padding: '28px', width: '460px', maxWidth: '92vw',
        display: 'flex', flexDirection: 'column', gap: '20px',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ color: '#fff', fontWeight: 700, fontSize: '15px', margin: 0 }}>
            Cargar Declaración de Importación (DIM)
          </h3>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#606075', padding: '4px' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Drop zone / file selector */}
        {!uploading && !result && (
          <label style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            gap: '10px', padding: '32px',
            border: '2px dashed rgba(96,165,250,0.3)', borderRadius: '12px',
            cursor: 'pointer', background: 'rgba(96,165,250,0.03)',
            transition: 'all 0.2s',
          }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(96,165,250,0.6)'; e.currentTarget.style.background = 'rgba(96,165,250,0.06)'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(96,165,250,0.3)'; e.currentTarget.style.background = 'rgba(96,165,250,0.03)'; }}
          >
            <FileUp size={32} style={{ color: '#60a5fa' }} />
            <div style={{ textAlign: 'center' }}>
              <p style={{ color: '#fff', fontWeight: 600, fontSize: '13px', margin: '0 0 4px' }}>
                Seleccioná el archivo DIM
              </p>
              <p style={{ color: '#606075', fontSize: '11px', margin: 0 }}>
                Solo archivos .pdf
              </p>
            </div>
            <input
              type="file"
              accept=".pdf"
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />
          </label>
        )}

        {/* Spinner de carga */}
        {uploading && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px', padding: '32px 0' }}>
            <div style={{
              width: 36, height: 36, borderRadius: '50%',
              border: '3px solid rgba(96,165,250,0.2)',
              borderTop: '3px solid #60a5fa',
              animation: 'spin 0.8s linear infinite',
            }} />
            <p style={{ color: '#606075', fontSize: '12px', margin: 0 }}>Procesando DIM...</p>
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </div>
        )}

        {/* Resultado */}
        {result && !uploading && (
          result.error ? (
            <div style={{
              display: 'flex', alignItems: 'flex-start', gap: '10px',
              background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)',
              borderRadius: '10px', padding: '14px',
            }}>
              <AlertCircle size={16} style={{ color: '#f87171', flexShrink: 0, marginTop: '1px' }} />
              <div>
                <p style={{ color: '#f87171', fontWeight: 700, fontSize: '12px', margin: '0 0 2px' }}>Error al procesar</p>
                <p style={{ color: '#f87171', fontSize: '11px', margin: 0, opacity: 0.8 }}>{result.error}</p>
              </div>
            </div>
          ) : (
            <div style={{
              background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)',
              borderRadius: '10px', padding: '16px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
                <CheckCircle size={15} style={{ color: '#22c55e' }} />
                <span style={{ color: '#22c55e', fontWeight: 700, fontSize: '12px' }}>DIM PROCESADA CORRECTAMENTE</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div style={{ textAlign: 'center', padding: '10px', background: 'rgba(34,197,94,0.06)', borderRadius: '8px' }}>
                  <p style={{ color: '#22c55e', fontWeight: 800, fontSize: '22px', margin: 0 }}>
                    {result.certificados_generados ?? result.generated ?? 0}
                  </p>
                  <p style={{ color: '#606075', fontSize: '10px', margin: '2px 0 0', fontWeight: 600 }}>Certificados generados</p>
                </div>
                <div style={{ textAlign: 'center', padding: '10px', background: 'rgba(249,115,22,0.06)', borderRadius: '8px' }}>
                  <p style={{ color: '#f97316', fontWeight: 800, fontSize: '22px', margin: 0 }}>
                    {result.vins_no_encontrados ?? result.not_found ?? 0}
                  </p>
                  <p style={{ color: '#606075', fontSize: '10px', margin: '2px 0 0', fontWeight: 600 }}>VINs no encontrados</p>
                </div>
              </div>
              {result.errors?.length > 0 && (
                <p style={{ color: '#f87171', fontSize: '11px', margin: '10px 0 0' }}>
                  {result.errors.length} fila(s) con errores
                </p>
              )}
            </div>
          )
        )}

        {/* Acciones */}
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 18px', borderRadius: '8px',
              border: '1px solid rgba(255,255,255,0.08)',
              background: 'transparent', color: '#606075',
              cursor: 'pointer', fontSize: '12px', fontWeight: 600,
            }}
          >
            {result ? 'Cerrar' : 'Cancelar'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Modal de edición de unidad
// ---------------------------------------------------------------------------
function EditUnitModal({ unit, onSave, onClose, saving }) {
  const [form, setForm] = useState({
    vin_number: unit.vin_number || '',
    engine_number: unit.engine_number || '',
    color: unit.color || '',
    model_year: unit.model_year || '',
  });

  const handleChange = (field, value) => setForm(f => ({ ...f, [field]: value }));

  const labelStyle = { display: 'block', color: '#9ca3af', fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '5px' };
  const inputStyle = {
    width: '100%', padding: '8px 10px', borderRadius: '8px', boxSizing: 'border-box',
    background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
    color: '#fff', fontSize: '12px', outline: 'none',
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1100,
      background: 'rgba(0,0,0,0.78)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#13131a', border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '16px', padding: '28px', width: '420px', maxWidth: '94vw',
        display: 'flex', flexDirection: 'column', gap: '18px',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ color: '#fff', fontWeight: 700, fontSize: '15px', margin: 0 }}>
            Editar unidad
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#606075', padding: '4px' }}>
            <X size={18} />
          </button>
        </div>

        {/* Info contextual */}
        <div style={{ background: 'rgba(96,165,250,0.06)', borderRadius: '8px', padding: '10px 12px' }}>
          <p style={{ margin: 0, fontSize: '10px', color: '#60a5fa', fontWeight: 700 }}>{unit.pi_number} — {unit.model || '—'}</p>
        </div>

        {/* Campos */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <label style={labelStyle}>VIN No.</label>
            <input style={inputStyle} value={form.vin_number} onChange={e => handleChange('vin_number', e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Motor No.</label>
            <input style={inputStyle} value={form.engine_number} onChange={e => handleChange('engine_number', e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Color</label>
            <input style={inputStyle} value={form.color} onChange={e => handleChange('color', e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Año Modelo</label>
            <input
              style={inputStyle}
              type="number"
              value={form.model_year}
              onChange={e => handleChange('model_year', e.target.value)}
              placeholder="Ej: 2025"
            />
          </div>
        </div>

        {/* Acciones */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
          <button
            onClick={onClose}
            disabled={saving}
            style={{
              padding: '8px 16px', borderRadius: '8px',
              border: '1px solid rgba(255,255,255,0.08)',
              background: 'transparent', color: '#606075',
              cursor: saving ? 'not-allowed' : 'pointer', fontSize: '12px', fontWeight: 600,
            }}
          >
            Cancelar
          </button>
          <button
            onClick={() => onSave(unit.id, form)}
            disabled={saving}
            style={{
              padding: '8px 18px', borderRadius: '8px', border: 'none',
              background: saving ? 'rgba(96,165,250,0.4)' : '#60a5fa',
              color: '#0d0d14', fontSize: '12px', fontWeight: 700,
              cursor: saving ? 'not-allowed' : 'pointer',
            }}
          >
            {saving ? 'Guardando...' : 'Guardar'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MotocicletasTab — componente principal
// ---------------------------------------------------------------------------
export default function MotocicletasTab({ userRole }) {
  const [units, setUnits] = useState([]);
  const [total, setTotal] = useState(0);
  const [totalGlobal, setTotalGlobal] = useState(0);
  const [totalEmpadronados, setTotalEmpadronados] = useState(0);
  const [totalPendientes, setTotalPendientes] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);

  // Filtros
  const [filterPI, setFilterPI] = useState('');
  const [filterModel, setFilterModel] = useState('');
  const [filterCertificado, setFilterCertificado] = useState(''); // '', 'true', 'false'

  // DIM upload
  const [showDimUpload, setShowDimUpload] = useState(false);
  const [dimUploading, setDimUploading] = useState(false);
  const [dimResult, setDimResult] = useState(null);

  // Edición inline
  const [editUnit, setEditUnit] = useState(null);
  const [editSaving, setEditSaving] = useState(false);

  // Toggle empadronamiento físico
  const [toggling, setToggling] = useState(null); // id de la unidad en proceso

  const PAGE_SIZE = 50;

  const fetchUnits = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page, page_size: PAGE_SIZE });
      if (filterPI) params.append('pi_number', filterPI);
      if (filterModel) params.append('model', filterModel);
      if (filterCertificado !== '') params.append('certificado_generado', filterCertificado);
      const res = await authFetch(`${API()}/imports/moto-units?${params}`);
      const data = await res.json();
      setUnits(data.items || []);
      setTotal(data.total || 0);
      setTotalGlobal(data.total_global ?? data.total ?? 0);
      setTotalEmpadronados(data.total_empadronados ?? 0);
      setTotalPendientes(data.total_pendientes ?? 0);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [page, filterPI, filterModel, filterCertificado]);

  useEffect(() => { fetchUnits(); }, [fetchUnits]);

  const handleDimUpload = async (file) => {
    setDimUploading(true);
    setDimResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await authFetch(`${API()}/imports/moto-units/dim`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        setDimResult({ error: data.detail || 'Error al procesar el DIM' });
      } else {
        setDimResult(data);
        fetchUnits();
      }
    } catch (e) {
      setDimResult({ error: 'Error de conexión' });
    } finally {
      setDimUploading(false);
    }
  };

  const handleEditSave = async (unitId, form) => {
    setEditSaving(true);
    try {
      const payload = {};
      if (form.vin_number.trim()) payload.vin_number = form.vin_number.trim();
      if (form.engine_number.trim()) payload.engine_number = form.engine_number.trim();
      if (form.color.trim()) payload.color = form.color.trim();
      if (form.model_year !== '' && form.model_year !== null) {
        const y = parseInt(form.model_year, 10);
        if (!isNaN(y)) payload.model_year = y;
      }
      const res = await authFetch(`${API()}/imports/moto-units/${unitId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || 'Error al guardar');
        return;
      }
      setEditUnit(null);
      fetchUnits();
    } catch (e) {
      alert('Error de conexión');
    } finally {
      setEditSaving(false);
    }
  };

  const handleToggleEmpadronamiento = async (unit) => {
    if (toggling) return;
    setToggling(unit.id);
    try {
      const nuevoValor = !unit.empadronamiento_fisico_enviado;
      const res = await authFetch(`${API()}/imports/moto-units/${unit.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ empadronamiento_fisico_enviado: nuevoValor }),
      });
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || 'Error al actualizar');
        return;
      }
      // Actualizar localmente sin refetch completo
      setUnits(prev => prev.map(u =>
        u.id === unit.id
          ? { ...u, empadronamiento_fisico_enviado: nuevoValor, empadronamiento_fisico_fecha: nuevoValor ? new Date().toISOString() : null }
          : u
      ));
    } catch (e) {
      alert('Error de conexión');
    } finally {
      setToggling(null);
    }
  };

  const handleDownloadCertificado = async (unit) => {
    try {
      const res = await authFetch(`${API()}/imports/moto-units/${unit.id}/certificado`);
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || 'Error al generar certificado');
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Certificado_${unit.vin_number}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert('Error al descargar el certificado');
    }
  };

  const handleOpenDim = (unit) => {
    const token = localStorage.getItem('um_token');
    const url = `${API()}/imports/moto-units/${unit.id}/dim-url?token=${token}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

      {/* KPIs — totales globales del backend */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
        {[
          { label: 'Total unidades', value: totalGlobal, color: '#60a5fa' },
          { label: 'Empadronadas', value: totalEmpadronados, color: '#22c55e' },
          { label: 'Pendientes', value: totalPendientes, color: '#f97316' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ padding: '14px 16px', borderRadius: '10px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
            <p style={{ margin: 0, fontSize: '18px', fontWeight: 800, color }}>{value}</p>
            <p style={{ margin: '2px 0 0', fontSize: '10px', color: '#606075', fontWeight: 600 }}>{label}</p>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
        {/* PI Number */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          padding: '6px 10px', borderRadius: '8px',
          background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)',
          minWidth: 160,
        }}>
          <Search size={11} color="#606075" />
          <input
            placeholder="Buscar PI Number..."
            value={filterPI}
            onChange={e => { setFilterPI(e.target.value); setPage(1); }}
            style={{ background: 'none', border: 'none', color: '#fff', fontSize: '11px', outline: 'none', flex: 1 }}
          />
        </div>

        {/* Modelo */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          padding: '6px 10px', borderRadius: '8px',
          background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)',
          minWidth: 140,
        }}>
          <Search size={11} color="#606075" />
          <input
            placeholder="Buscar modelo..."
            value={filterModel}
            onChange={e => { setFilterModel(e.target.value); setPage(1); }}
            style={{ background: 'none', border: 'none', color: '#fff', fontSize: '11px', outline: 'none', flex: 1 }}
          />
        </div>

        {/* Filtro empadronamiento */}
        <select
          value={filterCertificado}
          onChange={e => { setFilterCertificado(e.target.value); setPage(1); }}
          style={{
            padding: '6px 10px', borderRadius: '8px',
            background: '#1a1a24', border: '1px solid rgba(255,255,255,0.08)',
            color: filterCertificado === '' ? '#606075' : '#fff',
            fontSize: '11px', outline: 'none',
          }}
        >
          <option value="">Todos</option>
          <option value="true">Empadronados</option>
          <option value="false">Pendientes</option>
        </select>

        {/* Refresh */}
        <button
          onClick={() => fetchUnits()}
          style={{ padding: '6px 8px', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.07)', cursor: 'pointer', color: '#9ca3af' }}
        >
          <RefreshCw size={13} />
        </button>

        {/* Cargar DIM — solo superadmin */}
        {userRole === 'superadmin' && (
          <button
            onClick={() => { setDimResult(null); setShowDimUpload(true); }}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '7px 14px', borderRadius: '8px', border: 'none',
              background: 'rgba(96,165,250,0.12)', color: '#60a5fa',
              fontSize: '11px', fontWeight: 700, cursor: 'pointer',
              letterSpacing: '0.04em',
            }}
          >
            <FileUp size={13} /> Cargar DIM
          </button>
        )}

        {/* Contador */}
        <span style={{ fontSize: '11px', color: '#606075', marginLeft: 'auto' }}>
          {total} unidad{total !== 1 ? 'es' : ''} encontrada{total !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Tabla */}
      {loading ? (
        <p style={{ color: '#606075', fontSize: '12px', textAlign: 'center', margin: '40px 0' }}>Cargando unidades...</p>
      ) : units.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#606075' }}>
          <Bike size={36} style={{ margin: '0 auto 12px', display: 'block', opacity: 0.3 }} />
          <p style={{ fontSize: '13px', margin: 0 }}>No hay unidades cargadas</p>
          <p style={{ fontSize: '11px', margin: '4px 0 0', color: '#404050' }}>
            Importá un Packing List de Motos para ver las unidades
          </p>
        </div>
      ) : (
        <div style={{ overflowX: 'auto', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.06)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
            <thead>
              <tr style={{ background: '#0e0e14' }}>
                {['PI Number', 'Modelo', 'VIN', 'Motor No.', 'Color', 'Año Modelo', 'Empadronamiento', 'Empadr. Físico', 'Acciones'].map(h => (
                  <th
                    key={h}
                    style={{
                      padding: '9px 12px', textAlign: 'left',
                      fontSize: '9px', fontWeight: 700, color: '#606075',
                      textTransform: 'uppercase', letterSpacing: '0.07em',
                      borderBottom: '1px solid rgba(255,255,255,0.06)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {units.map((unit) => (
                <tr
                  key={unit.id}
                  style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <td style={{ padding: '9px 12px', color: '#60a5fa', fontWeight: 700, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                    {unit.pi_number || '—'}
                  </td>
                  <td style={{ padding: '9px 12px', color: '#e2e8f0', whiteSpace: 'nowrap' }}>
                    {unit.model || unit.modelo || '—'}
                  </td>
                  <td style={{ padding: '9px 12px', color: '#d1d5db', fontFamily: 'monospace', fontSize: '10px', whiteSpace: 'nowrap' }}>
                    {unit.vin_number || unit.vin || '—'}
                  </td>
                  <td style={{ padding: '9px 12px', color: '#9ca3af', fontFamily: 'monospace', fontSize: '10px', whiteSpace: 'nowrap' }}>
                    {unit.engine_number || unit.motor_number || '—'}
                  </td>
                  <td style={{ padding: '9px 12px', color: '#9ca3af', whiteSpace: 'nowrap' }}>
                    {unit.color || '—'}
                  </td>
                  <td style={{ padding: '9px 12px', color: '#9ca3af', whiteSpace: 'nowrap' }}>
                    {unit.model_year || '—'}
                  </td>
                  <td style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <CertBadge generated={unit.certificado_generado} />
                      {unit.certificado_generado && (
                        <button
                          onClick={() => handleDownloadCertificado(unit)}
                          title="Descargar certificado de empadronamiento"
                          style={{
                            display: 'flex', alignItems: 'center', gap: '4px',
                            padding: '3px 8px', borderRadius: '6px', border: 'none',
                            background: 'rgba(34,197,94,0.1)', color: '#22c55e',
                            fontSize: '10px', fontWeight: 700, cursor: 'pointer',
                          }}
                        >
                          <Download size={11} />
                        </button>
                      )}
                      {unit.dim_pdf_object_name && (
                        <button
                          onClick={() => handleOpenDim(unit)}
                          title="Ver Declaración de Importación (DIM)"
                          style={{
                            display: 'flex', alignItems: 'center', gap: '4px',
                            padding: '3px 8px', borderRadius: '6px', border: 'none',
                            background: 'rgba(96,165,250,0.1)', color: '#60a5fa',
                            fontSize: '10px', fontWeight: 700, cursor: 'pointer',
                          }}
                        >
                          <FileText size={11} /> DIM
                        </button>
                      )}
                    </div>
                  </td>
                  <td style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
                    {userRole === 'superadmin' ? (
                      <button
                        onClick={() => handleToggleEmpadronamiento(unit)}
                        disabled={toggling === unit.id}
                        title={unit.empadronamiento_fisico_enviado
                          ? `Enviado${unit.empadronamiento_fisico_fecha ? ' el ' + new Date(unit.empadronamiento_fisico_fecha).toLocaleDateString('es-CO') : ''}`
                          : 'Marcar como enviado al distribuidor'}
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: '5px',
                          padding: '3px 10px', borderRadius: '20px', border: 'none',
                          cursor: toggling === unit.id ? 'not-allowed' : 'pointer',
                          fontSize: '9px', fontWeight: 700, letterSpacing: '0.04em',
                          transition: 'all 0.15s',
                          ...(unit.empadronamiento_fisico_enviado
                            ? { background: 'rgba(34,197,94,0.12)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.3)' }
                            : { background: 'rgba(96,96,117,0.12)', color: '#606075', border: '1px solid rgba(96,96,117,0.25)' }
                          ),
                        }}
                      >
                        {toggling === unit.id
                          ? '...'
                          : unit.empadronamiento_fisico_enviado
                            ? <><Send size={9} /> ENVIADO</>
                            : <><Send size={9} /> PENDIENTE</>
                        }
                      </button>
                    ) : (
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: '4px',
                        fontSize: '9px', fontWeight: 700, padding: '2px 8px', borderRadius: '20px',
                        ...(unit.empadronamiento_fisico_enviado
                          ? { background: 'rgba(34,197,94,0.1)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.25)' }
                          : { background: 'rgba(96,96,117,0.1)', color: '#606075', border: '1px solid rgba(96,96,117,0.2)' }
                        ),
                      }}>
                        <Send size={9} />
                        {unit.empadronamiento_fisico_enviado ? 'ENVIADO' : 'PENDIENTE'}
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
                    <button
                      onClick={() => setEditUnit(unit)}
                      title="Editar unidad"
                      style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        padding: '4px 8px', borderRadius: '6px', border: 'none',
                        background: 'rgba(255,255,255,0.06)', color: '#9ca3af',
                        cursor: 'pointer', transition: 'all 0.15s',
                      }}
                      onMouseEnter={e => { e.currentTarget.style.background = 'rgba(96,165,250,0.15)'; e.currentTarget.style.color = '#60a5fa'; }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; e.currentTarget.style.color = '#9ca3af'; }}
                    >
                      <Pencil size={12} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Paginación */}
      {total > PAGE_SIZE && (
        <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', alignItems: 'center' }}>
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            style={{
              padding: '5px 12px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.08)',
              background: 'transparent', color: page === 1 ? '#404050' : '#9ca3af',
              cursor: page === 1 ? 'not-allowed' : 'pointer', fontSize: '11px',
            }}
          >
            ← Anterior
          </button>
          <span style={{ color: '#606075', fontSize: '11px' }}>
            Pág. {page} / {Math.ceil(total / PAGE_SIZE)}
          </span>
          <button
            onClick={() => setPage(p => p + 1)}
            disabled={page >= Math.ceil(total / PAGE_SIZE)}
            style={{
              padding: '5px 12px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.08)',
              background: 'transparent', color: page >= Math.ceil(total / PAGE_SIZE) ? '#404050' : '#9ca3af',
              cursor: page >= Math.ceil(total / PAGE_SIZE) ? 'not-allowed' : 'pointer', fontSize: '11px',
            }}
          >
            Siguiente →
          </button>
        </div>
      )}

      {/* Modal DIM */}
      {showDimUpload && (
        <DimUploadModal
          onUpload={handleDimUpload}
          onClose={() => setShowDimUpload(false)}
          uploading={dimUploading}
          result={dimResult}
        />
      )}

      {/* Modal edición de unidad */}
      {editUnit && (
        <EditUnitModal
          unit={editUnit}
          onSave={handleEditSave}
          onClose={() => setEditUnit(null)}
          saving={editSaving}
        />
      )}
    </div>
  );
}
