'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import AdminLayout from '../admin-layout';
import { UploadCloud, Image as ImageIcon, Save, Trash2, Clock, Bike, Plus, Pencil, X, AlertCircle, BookOpen, Upload, FileText, Loader2, ChevronDown } from 'lucide-react';
import { authFetch } from '../../lib/authFetch';

const BACKEND_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace('http://', 'https://');

const VM_FORM_DEFAULTS = {
  modelo: '',
  marca: 'UM',
  cilindrada: '',
  potencia: '',
  peso: '',
  vueltas_aire: '',
  posicion_cortina: '',
  sistemas_control: '',
  combustible: 'CARBURADOR',
  largo_total: '',
  ancho_total: '',
  altura_total: '',
  altura_silla: '',
  distancia_suelo: '',
  distancia_ejes: '',
  tanque_combustible: '',
  relacion_compresion: '',
  llanta_delantera: '',
  llanta_trasera: '',
};

export default function SettingsPage() {
  const [logoBase64, setLogoBase64] = useState(null);
  const [successMsg, setSuccessMsg] = useState('');
  const [userRole, setUserRole] = useState(null);

  // Catálogo de partes — carga de PDFs
  const [catalogModels, setCatalogModels]       = useState([]);
  const [catalogModelsLoading, setCatalogModelsLoading] = useState(true);
  const [catVehicleModel, setCatVehicleModel]   = useState('');
  const [catModelCode, setCatModelCode]         = useState('');
  const [catCodeAutoFilled, setCatCodeAutoFilled] = useState(false);
  const [catFiles, setCatFiles]                 = useState([]);
  const [catResults, setCatResults]             = useState([]);
  const [catLoading, setCatLoading]             = useState(false);
  const [catProgress, setCatProgress]           = useState({ done: 0, total: 0 });
  const catFileRef = useRef();

  const handleCatVehicleModelChange = (value) => {
    setCatVehicleModel(value);
    setCatResults([]);
    const match = catalogModels.find(m => m.vehicle_model === value);
    if (match?.catalog_model_code) {
      setCatModelCode(match.catalog_model_code);
      setCatCodeAutoFilled(true);
    } else {
      setCatModelCode('');
      setCatCodeAutoFilled(false);
    }
  };

  const handleCatFiles = (e) => {
    const selected = Array.from(e.target.files).filter(f => f.name.endsWith('.pdf'));
    setCatFiles(selected);
    setCatResults([]);
  };

  const handleCatDrop = (e) => {
    e.preventDefault();
    const dropped = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.pdf'));
    setCatFiles(dropped);
    setCatResults([]);
  };

  const handleCatUpload = async () => {
    if (!catModelCode.trim() || !catVehicleModel || catFiles.length === 0) return;
    setCatLoading(true);
    setCatResults([]);
    setCatProgress({ done: 0, total: catFiles.length });
    const newResults = [];
    for (let i = 0; i < catFiles.length; i++) {
      const file = catFiles[i];
      const fd = new FormData();
      fd.append('pdf_file', file);
      fd.append('model_code', catModelCode.trim());
      fd.append('vehicle_model', catVehicleModel);
      try {
        const res = await authFetch('/parts/admin/load-section', { method: 'POST', body: fd });
        if (res.ok) {
          const data = await res.json();
          newResults.push({ filename: file.name, status: 'ok', ...data });
        } else {
          const err = await res.json().catch(() => ({ detail: 'Error desconocido' }));
          newResults.push({ filename: file.name, status: 'error', error: err.detail });
        }
      } catch (e) {
        newResults.push({ filename: file.name, status: 'error', error: e.message });
      }
      setCatProgress({ done: i + 1, total: catFiles.length });
      setCatResults([...newResults]);
    }
    setCatLoading(false);
  };

  const catPct = catProgress.total > 0 ? Math.round((catProgress.done / catProgress.total) * 100) : 0;
  const catCanUpload = !catLoading && catModelCode.trim() && catVehicleModel && catFiles.length > 0;
  const catSuccess = catResults.filter(r => r.status === 'ok').length;
  const catErrors  = catResults.filter(r => r.status === 'error').length;
  const catTotalParts = catResults.filter(r => r.status === 'ok').reduce((s, r) => s + (r.parts_loaded || 0), 0);
  const catTotalRefs  = catResults.filter(r => r.status === 'ok').reduce((s, r) => s + (r.references_new || 0), 0);

  // Variables del sistema
  const [reminderMinutes, setReminderMinutes] = useState(60);
  const [reminderSaving, setReminderSaving] = useState(false);
  const [reminderMsg, setReminderMsg] = useState('');

  // Modelos de Vehículos
  const [vehicleModels, setVehicleModels] = useState([]);
  const [vmLoading, setVmLoading] = useState(false);
  const [showVMModal, setShowVMModal] = useState(false);
  const [editingVM, setEditingVM] = useState(null);
  const [vmForm, setVmForm] = useState(VM_FORM_DEFAULTS);
  const [vmSaving, setVmSaving] = useState(false);
  const [vmError, setVmError] = useState('');

  const fetchVehicleModels = useCallback(async () => {
    setVmLoading(true);
    try {
      const res = await authFetch(`${BACKEND_URL}/vehicle-models`);
      if (res.ok) {
        const data = await res.json();
        setVehicleModels(Array.isArray(data) ? data : (data.items || []));
      }
    } catch (e) {
      console.error('Error cargando modelos:', e);
    } finally {
      setVmLoading(false);
    }
  }, []);

  const saveVehicleModel = async () => {
    if (!vmForm.modelo.trim()) { setVmError('El campo Modelo es obligatorio.'); return; }
    setVmSaving(true);
    setVmError('');
    try {
      const payload = { ...vmForm };
      const url = editingVM
        ? `${BACKEND_URL}/vehicle-models/${editingVM.id}`
        : `${BACKEND_URL}/vehicle-models`;
      const method = editingVM ? 'PUT' : 'POST';
      const res = await authFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setShowVMModal(false);
        setEditingVM(null);
        setVmForm(VM_FORM_DEFAULTS);
        fetchVehicleModels();
      } else {
        const err = await res.json().catch(() => ({}));
        setVmError(err.detail || 'Error al guardar el modelo.');
      }
    } catch (e) {
      setVmError('Error de conexión.');
    } finally {
      setVmSaving(false);
    }
  };

  const deleteVehicleModel = async (vm) => {
    if (!confirm(`¿Eliminar el modelo "${vm.modelo}"? Esta acción no se puede deshacer.`)) return;
    try {
      await authFetch(`${BACKEND_URL}/vehicle-models/${vm.id}`, { method: 'DELETE' });
      fetchVehicleModels();
    } catch (e) {
      alert('Error al eliminar el modelo.');
    }
  };

  const openCreateVM = () => {
    setEditingVM(null);
    setVmForm(VM_FORM_DEFAULTS);
    setVmError('');
    setShowVMModal(true);
  };

  const openEditVM = (vm) => {
    setEditingVM(vm);
    setVmForm({
      modelo: vm.modelo || '',
      marca: vm.marca || 'UM',
      cilindrada: vm.cilindrada || '',
      potencia: vm.potencia || '',
      peso: vm.peso || '',
      vueltas_aire: vm.vueltas_aire || '',
      posicion_cortina: vm.posicion_cortina || '',
      sistemas_control: vm.sistemas_control || '',
      combustible: vm.combustible || 'CARBURADOR',
      largo_total: vm.largo_total || '',
      ancho_total: vm.ancho_total || '',
      altura_total: vm.altura_total || '',
      altura_silla: vm.altura_silla || '',
      distancia_suelo: vm.distancia_suelo || '',
      distancia_ejes: vm.distancia_ejes || '',
      tanque_combustible: vm.tanque_combustible || '',
      relacion_compresion: vm.relacion_compresion || '',
      llanta_delantera: vm.llanta_delantera || '',
      llanta_trasera: vm.llanta_trasera || '',
    });
    setVmError('');
    setShowVMModal(true);
  };

  useEffect(() => {
    const savedLogo = localStorage.getItem('um_logo');
    if (savedLogo) setLogoBase64(savedLogo);

    // Detectar rol
    try {
      const user = JSON.parse(sessionStorage.getItem('um_user') || '{}');
      setUserRole(user.role || null);
    } catch { setUserRole(null); }

    // Cargar logo global de la marca
    fetch(`${BACKEND_URL}/settings/logo`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.logo_base64) {
          setLogoBase64(data.logo_base64);
          localStorage.setItem('um_logo', data.logo_base64);
        }
      })
      .catch(() => {});

    // Cargar config del taller
    const tenantId = sessionStorage.getItem('um_tenant_id');
    if (tenantId) {
      fetch(`${BACKEND_URL}/tenants/${tenantId}/config`, {
        headers: { Authorization: `Bearer ${sessionStorage.getItem('um_token') || ''}` }
      })
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data?.diagnosis_reminder_minutes) setReminderMinutes(data.diagnosis_reminder_minutes); })
        .catch(() => {});
    }
  }, []);

  useEffect(() => { fetchVehicleModels(); }, [fetchVehicleModels]);

  useEffect(() => {
    authFetch('/parts/admin/vehicle-models')
      .then(r => r.ok ? r.json() : [])
      .then(data => setCatalogModels(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setCatalogModelsLoading(false));
  }, []);

  const handleLogoUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (file.size > 2 * 1024 * 1024) {
      alert('El archivo es muy pesado. Máximo 2MB.');
      return;
    }

    const reader = new FileReader();
    reader.onload = (event) => {
      setLogoBase64(event.target.result);
    };
    reader.readAsDataURL(file);
  };

  const handleSaveLogo = async () => {
    if (!logoBase64) return;
    try {
      const res = await fetch(`${BACKEND_URL}/settings/logo`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${sessionStorage.getItem('um_token') || ''}` },
        body: JSON.stringify({ logo_base64: logoBase64 }),
      });
      if (res.ok) {
        localStorage.setItem('um_logo', logoBase64);
        window.dispatchEvent(new Event('storage'));
        setSuccessMsg('✅ Logotipo guardado correctamente.');
      } else {
        setSuccessMsg('⚠️ Error al guardar el logo.');
      }
    } catch {
      setSuccessMsg('⚠️ Error de conexión.');
    }
    setTimeout(() => setSuccessMsg(''), 5000);
  };

  const handleSaveReminder = async () => {
    if (reminderMinutes < 5) {
      setReminderMsg('El valor mínimo es 5 minutos.');
      return;
    }
    const tenantId = sessionStorage.getItem('um_tenant_id');
    if (!tenantId) { setReminderMsg('No se encontró el taller activo.'); return; }

    setReminderSaving(true);
    try {
      const res = await fetch(`${BACKEND_URL}/tenants/${tenantId}/config`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${sessionStorage.getItem('um_token') || ''}`
        },
        body: JSON.stringify({ diagnosis_reminder_minutes: Number(reminderMinutes) })
      });
      if (res.ok) {
        setReminderMsg('✅ Guardado correctamente.');
      } else {
        setReminderMsg('⚠️ Error al guardar. Intentá de nuevo.');
      }
    } catch {
      setReminderMsg('⚠️ Error de conexión.');
    } finally {
      setReminderSaving(false);
      setTimeout(() => setReminderMsg(''), 4000);
    }
  };

  const handleRemoveLogo = async () => {
    await fetch(`${BACKEND_URL}/settings/logo`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${sessionStorage.getItem('um_token') || ''}` },
      body: JSON.stringify({ logo_base64: null }),
    }).catch(() => {});
    setLogoBase64(null);
    localStorage.removeItem('um_logo');
    window.dispatchEvent(new Event('storage'));
    setSuccessMsg('Logotipo eliminado.');
    setTimeout(() => setSuccessMsg(''), 5000);
  };

  return (
    <AdminLayout>
      <header className="page-header">
        <div>
          <h1 className="page-title">Configuración del <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Sistema</span></h1>
          <p className="page-subtitle">Personalización visual y parametrización de variables del sistema</p>
        </div>
      </header>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
        
        {/* Fila: Identidad Visual + Variables del Sistema */}
        <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'stretch', flexWrap: 'wrap' }}>

          {/* Identidad Visual — compacto */}
          <section className="glass p-6" style={{ flex: '1 1 320px', minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '1rem', paddingBottom: '0.75rem', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <ImageIcon size={16} style={{ color: '#ff5f33', flexShrink: 0 }} />
              <h2 style={{ fontSize: '0.8rem', fontWeight: 700, color: '#fff', margin: 0, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Identidad Visual</h2>
            </div>

            <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
              {/* Controles */}
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.6rem', minWidth: 0 }}>
                <label
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', padding: '0.65rem 1rem', border: '1px dashed rgba(255,255,255,0.2)', borderRadius: '0.75rem', cursor: 'pointer', background: 'rgba(255,255,255,0.02)', fontSize: '0.72rem', fontWeight: 700, color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', letterSpacing: '0.05em' }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = '#ff5f33'; e.currentTarget.style.color = '#ff5f33'; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.2)'; e.currentTarget.style.color = 'rgba(255,255,255,0.5)'; }}
                >
                  <UploadCloud size={15} />
                  <span>Seleccionar imagen</span>
                  <input type="file" style={{ display: 'none' }} accept="image/png, image/jpeg, image/svg+xml, image/webp" onChange={handleLogoUpload} />
                </label>

                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button className="btn-primary" onClick={handleSaveLogo} disabled={!logoBase64} style={{ flex: 1, padding: '0.45rem 0.75rem', fontSize: '0.68rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.35rem' }}>
                    <Save size={13} /> Guardar
                  </button>
                  <button className="btn" onClick={handleRemoveLogo} disabled={!logoBase64} style={{ flex: 1, padding: '0.45rem 0.75rem', fontSize: '0.68rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.35rem', borderColor: 'rgba(239,68,68,0.25)', color: '#ef4444' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'rgba(239,68,68,0.1)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
                  >
                    <Trash2 size={13} /> Restaurar
                  </button>
                </div>

                {successMsg && <p style={{ color: '#4ade80', fontSize: '0.68rem', margin: 0 }}>{successMsg}</p>}
              </div>

              {/* Preview */}
              <div style={{ width: '110px', height: '72px', background: 'rgba(0,0,0,0.35)', borderRadius: '0.75rem', border: '1px solid rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                {logoBase64 ? (
                  <img src={logoBase64} alt="preview" style={{ maxHeight: '52px', maxWidth: '90px', objectFit: 'contain' }} />
                ) : (
                  <div style={{ opacity: 0.25, display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                    <div style={{ width: '26px', height: '26px', background: '#ff5f33', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <span style={{ color: '#fff', fontWeight: 900, fontSize: '0.6rem', fontStyle: 'italic' }}>UM</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </section>

          {/* Variables del Sistema */}
          <section className="glass p-6" style={{ flex: '1 1 280px', minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '1rem', paddingBottom: '0.75rem', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <Clock size={16} style={{ color: '#ff5f33', flexShrink: 0 }} />
              <h2 style={{ fontSize: '0.8rem', fontWeight: 700, color: '#fff', margin: 0, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Variables del Sistema</h2>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
              <label style={{ fontSize: '0.78rem', fontWeight: 600, color: '#fff' }}>
                Recordatorio de diagnóstico
              </label>
              <p style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.3)', margin: 0, lineHeight: 1.6 }}>
                Tiempo que espera Sonia antes de preguntarle al técnico qué encontró. Mínimo 5 min.
              </p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginTop: '0.25rem', flexWrap: 'wrap' }}>
                <input
                  type="number"
                  min={5}
                  max={480}
                  value={reminderMinutes}
                  onChange={e => setReminderMinutes(Number(e.target.value))}
                  style={{ width: '72px', padding: '0.45rem 0.65rem', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', fontSize: '0.85rem', outline: 'none' }}
                />
                <span style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.35)' }}>minutos</span>
                <button className="btn-primary" onClick={handleSaveReminder} disabled={reminderSaving} style={{ padding: '0.45rem 1rem', fontSize: '0.68rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                  <Save size={13} />
                  {reminderSaving ? 'Guardando...' : 'Guardar'}
                </button>
              </div>
              {reminderMsg && <p style={{ color: '#4ade80', fontSize: '0.68rem', margin: 0 }}>{reminderMsg}</p>}
            </div>
          </section>

        </div>

        {/* Sección: Modelos de Vehículos */}
        <section className="glass p-6">
          <div className="flex items-center justify-between mb-6 border-b border-white/5 pb-4">
            <div className="flex items-center space-x-3">
              <Bike size={20} className="text-orange-500" />
              <h2 className="text-lg font-bold">Modelos de Vehículos</h2>
            </div>
            {userRole === 'superadmin' && (
              <button
                onClick={openCreateVM}
                style={{
                  display: 'flex', alignItems: 'center', gap: '6px',
                  padding: '7px 14px', borderRadius: '8px', border: 'none',
                  background: 'rgba(34,197,94,0.12)', color: '#22c55e',
                  fontSize: '12px', fontWeight: 700, cursor: 'pointer',
                  letterSpacing: '0.04em',
                }}
              >
                <Plus size={14} /> Nuevo Modelo
              </button>
            )}
          </div>

          {vmLoading ? (
            <p style={{ color: '#606075', fontSize: '12px', textAlign: 'center', margin: '32px 0' }}>Cargando modelos...</p>
          ) : vehicleModels.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '48px 0', color: '#606075' }}>
              <Bike size={32} style={{ margin: '0 auto 10px', display: 'block', opacity: 0.3 }} />
              <p style={{ fontSize: '13px', margin: 0 }}>No hay modelos cargados</p>
            </div>
          ) : (
            <div style={{ overflowX: 'auto', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.06)' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead>
                  <tr style={{ background: 'rgba(0,0,0,0.3)' }}>
                    {['Modelo', 'Marca', 'Cilindrada', 'Potencia', 'Combustible', ''].map(h => (
                      <th key={h} style={{
                        padding: '9px 14px', textAlign: 'left',
                        fontSize: '9px', fontWeight: 700, color: '#606075',
                        textTransform: 'uppercase', letterSpacing: '0.07em',
                        borderBottom: '1px solid rgba(255,255,255,0.06)',
                        whiteSpace: 'nowrap',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {vehicleModels.map((vm) => (
                    <tr
                      key={vm.id}
                      style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}
                      onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                      <td style={{ padding: '10px 14px', color: '#e2e8f0', fontWeight: 700 }}>{vm.modelo}</td>
                      <td style={{ padding: '10px 14px', color: '#9ca3af' }}>{vm.marca || '—'}</td>
                      <td style={{ padding: '10px 14px', color: '#9ca3af' }}>{vm.cilindrada || '—'}</td>
                      <td style={{ padding: '10px 14px', color: '#9ca3af' }}>{vm.potencia || '—'}</td>
                      <td style={{ padding: '10px 14px' }}>
                        {vm.combustible && (
                          <span style={{
                            fontSize: '9px', fontWeight: 700, padding: '2px 8px', borderRadius: '20px',
                            background: vm.combustible === 'INYECCION' ? 'rgba(96,165,250,0.1)' : 'rgba(249,115,22,0.1)',
                            color: vm.combustible === 'INYECCION' ? '#60a5fa' : '#f97316',
                            border: `1px solid ${vm.combustible === 'INYECCION' ? 'rgba(96,165,250,0.25)' : 'rgba(249,115,22,0.25)'}`,
                          }}>
                            {vm.combustible}
                          </span>
                        )}
                        {!vm.combustible && <span style={{ color: '#606075' }}>—</span>}
                      </td>
                      {userRole === 'superadmin' ? (
                        <td style={{ padding: '10px 14px' }}>
                          <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
                            <button
                              onClick={() => openEditVM(vm)}
                              title="Editar"
                              style={{
                                padding: '4px 8px', borderRadius: '6px', border: 'none',
                                background: 'rgba(96,165,250,0.1)', color: '#60a5fa',
                                cursor: 'pointer', display: 'flex', alignItems: 'center',
                              }}
                            >
                              <Pencil size={12} />
                            </button>
                            <button
                              onClick={() => deleteVehicleModel(vm)}
                              title="Eliminar"
                              style={{
                                padding: '4px 8px', borderRadius: '6px', border: 'none',
                                background: 'rgba(248,113,113,0.1)', color: '#f87171',
                                cursor: 'pointer', display: 'flex', alignItems: 'center',
                              }}
                            >
                              <Trash2 size={12} />
                            </button>
                          </div>
                        </td>
                      ) : (
                        <td />
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Sección: Carga de Catálogo de Partes */}
        <section className="glass p-6">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '1.25rem', paddingBottom: '0.75rem', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
            <BookOpen size={16} style={{ color: '#ff5f33', flexShrink: 0 }} />
            <h2 style={{ fontSize: '0.8rem', fontWeight: 700, color: '#fff', margin: 0, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Carga de Catálogo de Partes</h2>
          </div>

          {/* Modelo + Código */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
            <div>
              <label style={catLabel}>Modelo del vehículo *</label>
              {catalogModelsLoading ? (
                <input disabled placeholder="Cargando..." style={{ ...catInput, opacity: 0.5 }} />
              ) : catalogModels.length > 0 ? (
                <div style={{ position: 'relative' }}>
                  <select value={catVehicleModel} onChange={e => handleCatVehicleModelChange(e.target.value)} disabled={catLoading} style={{ ...catInput, appearance: 'none', paddingRight: '2.5rem', cursor: 'pointer' }}>
                    <option value="">— Seleccioná un modelo —</option>
                    {catalogModels.map(m => (
                      <option key={m.vehicle_model} value={m.vehicle_model}>{m.vehicle_model}{m.catalog_model_code ? ' ✓' : ''}</option>
                    ))}
                  </select>
                  <ChevronDown size={13} color="#606075" style={{ position: 'absolute', right: '0.75rem', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
                </div>
              ) : (
                <input value={catVehicleModel} onChange={e => handleCatVehicleModelChange(e.target.value)} placeholder="Ej: Renegade Sport 200S" disabled={catLoading} style={catInput} />
              )}
            </div>
            <div>
              <label style={catLabel}>
                Código interno *
                {catCodeAutoFilled && <span style={{ marginLeft: '0.4rem', fontSize: '0.55rem', color: '#10b981', fontWeight: 700 }}>AUTO</span>}
              </label>
              <input value={catModelCode} onChange={e => { setCatModelCode(e.target.value); setCatCodeAutoFilled(false); }} placeholder="ej: renegade_200_sport" disabled={catLoading} style={catInput} />
            </div>
          </div>

          {/* Drop zone */}
          <div
            onDragOver={e => e.preventDefault()} onDrop={handleCatDrop}
            onClick={() => !catLoading && catFileRef.current?.click()}
            style={{ borderRadius: '12px', padding: '1.5rem', marginBottom: '1rem', border: '2px dashed rgba(255,255,255,0.08)', textAlign: 'center', cursor: catLoading ? 'default' : 'pointer', transition: 'border-color 0.2s' }}
            onMouseEnter={e => { if (!catLoading) e.currentTarget.style.borderColor = 'rgba(255,95,51,0.3)'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)'; }}
          >
            <Upload size={22} color="#606075" style={{ marginBottom: '0.5rem' }} />
            <p style={{ margin: '0 0 0.2rem', fontSize: '0.75rem', fontWeight: 700, color: '#fff' }}>Arrastrá los PDFs acá o hacé click</p>
            <p style={{ margin: 0, fontSize: '0.62rem', color: '#606075' }}>Múltiples archivos · Solo .pdf</p>
            <input ref={catFileRef} type="file" multiple accept=".pdf" onChange={handleCatFiles} style={{ display: 'none' }} />
          </div>

          {/* Lista archivos */}
          {catFiles.length > 0 && (
            <div style={{ marginBottom: '1rem', display: 'flex', flexDirection: 'column', gap: '0.4rem', maxHeight: '180px', overflowY: 'auto' }}>
              {catFiles.map((f, i) => {
                const result = catResults.find(r => r.filename === f.name);
                return (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', padding: '0.5rem 0.75rem', borderRadius: '8px', background: 'rgba(255,255,255,0.03)', border: `1px solid ${result?.status === 'ok' ? 'rgba(16,185,129,0.15)' : result?.status === 'error' ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.05)'}` }}>
                    <FileText size={13} color={result?.status === 'ok' ? '#10b981' : result?.status === 'error' ? '#ef4444' : '#606075'} />
                    <span style={{ flex: 1, fontSize: '0.7rem', color: '#ccc', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                    {result?.status === 'ok' && <span style={{ fontSize: '0.58rem', color: '#10b981', fontWeight: 700 }}>✓ {result.parts_loaded} items</span>}
                    {result?.status === 'error' && <span style={{ fontSize: '0.58rem', color: '#ef4444', fontWeight: 700 }}>✗ {result.error}</span>}
                    {catLoading && !result && <Loader2 size={12} color="#ff5f33" style={{ animation: 'spin 1s linear infinite', flexShrink: 0 }} />}
                  </div>
                );
              })}
            </div>
          )}

          {/* Progress */}
          {catLoading && (
            <div style={{ marginBottom: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                <span style={{ fontSize: '0.68rem', color: '#fff', fontWeight: 700 }}>Procesando {catProgress.done} de {catProgress.total}...</span>
                <span style={{ fontSize: '0.68rem', color: '#ff5f33', fontWeight: 700 }}>{catPct}%</span>
              </div>
              <div style={{ height: '5px', borderRadius: '99px', background: 'rgba(255,255,255,0.06)' }}>
                <div style={{ height: '100%', width: `${catPct}%`, borderRadius: '99px', background: '#ff5f33', transition: 'width 0.3s ease' }} />
              </div>
            </div>
          )}

          {/* Botón + Resumen */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
            <button onClick={handleCatUpload} disabled={!catCanUpload} style={{ padding: '0.65rem 1.5rem', borderRadius: '10px', border: 'none', cursor: catCanUpload ? 'pointer' : 'not-allowed', background: catCanUpload ? '#ff5f33' : 'rgba(255,95,51,0.2)', color: '#fff', fontWeight: 900, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              {catLoading ? <><Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> Cargando...</> : <><Upload size={13} /> Cargar {catFiles.length > 0 ? `${catFiles.length} PDF${catFiles.length !== 1 ? 's' : ''}` : 'PDFs'}</>}
            </button>
            {catResults.length > 0 && !catLoading && (
              <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '0.68rem', color: '#10b981', fontWeight: 700 }}>✓ {catSuccess} secciones</span>
                <span style={{ fontSize: '0.68rem', color: '#ff5f33', fontWeight: 700 }}>{catTotalRefs} refs nuevas</span>
                <span style={{ fontSize: '0.68rem', color: '#6366f1', fontWeight: 700 }}>{catTotalParts} items</span>
                {catErrors > 0 && <span style={{ fontSize: '0.68rem', color: '#ef4444', fontWeight: 700 }}>✗ {catErrors} errores</span>}
              </div>
            )}
          </div>
        </section>

      </div>

      {/* Modal Crear / Editar Modelo de Vehículo */}
      {showVMModal && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '16px',
        }}>
          <div style={{
            background: '#13131a', border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: '16px', padding: '28px',
            width: '560px', maxWidth: '100%', maxHeight: '90vh',
            overflowY: 'auto',
            display: 'flex', flexDirection: 'column', gap: '20px',
          }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ color: '#fff', fontWeight: 700, fontSize: '15px', margin: 0 }}>
                {editingVM ? 'Editar Modelo' : 'Nuevo Modelo de Vehículo'}
              </h3>
              <button
                onClick={() => setShowVMModal(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#606075', padding: '4px' }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Formulario */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              {/* Modelo * */}
              <div style={{ gridColumn: '1 / -1', display: 'flex', flexDirection: 'column', gap: '5px' }}>
                <label style={{ fontSize: '11px', fontWeight: 600, color: '#9ca3af' }}>
                  Modelo <span style={{ color: '#f87171' }}>*</span>
                </label>
                <input
                  value={vmForm.modelo}
                  onChange={e => setVmForm(f => ({ ...f, modelo: e.target.value }))}
                  placeholder="Ej: YX-200"
                  style={{
                    padding: '8px 12px', borderRadius: '8px', fontSize: '13px',
                    background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                    color: '#fff', outline: 'none',
                  }}
                  onFocus={e => e.target.style.borderColor = '#60a5fa'}
                  onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.1)'}
                />
              </div>

              {/* Marca */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                <label style={{ fontSize: '11px', fontWeight: 600, color: '#9ca3af' }}>Marca</label>
                <input
                  value={vmForm.marca}
                  onChange={e => setVmForm(f => ({ ...f, marca: e.target.value }))}
                  placeholder="UM"
                  style={{
                    padding: '8px 12px', borderRadius: '8px', fontSize: '13px',
                    background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                    color: '#fff', outline: 'none',
                  }}
                  onFocus={e => e.target.style.borderColor = '#60a5fa'}
                  onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.1)'}
                />
              </div>

              {/* Cilindrada */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                <label style={{ fontSize: '11px', fontWeight: 600, color: '#9ca3af' }}>Cilindrada</label>
                <input
                  value={vmForm.cilindrada}
                  onChange={e => setVmForm(f => ({ ...f, cilindrada: e.target.value }))}
                  placeholder="196cc"
                  style={{
                    padding: '8px 12px', borderRadius: '8px', fontSize: '13px',
                    background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                    color: '#fff', outline: 'none',
                  }}
                  onFocus={e => e.target.style.borderColor = '#60a5fa'}
                  onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.1)'}
                />
              </div>

              {/* Potencia */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                <label style={{ fontSize: '11px', fontWeight: 600, color: '#9ca3af' }}>Potencia</label>
                <input
                  value={vmForm.potencia}
                  onChange={e => setVmForm(f => ({ ...f, potencia: e.target.value }))}
                  placeholder="13.41 HP"
                  style={{
                    padding: '8px 12px', borderRadius: '8px', fontSize: '13px',
                    background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                    color: '#fff', outline: 'none',
                  }}
                  onFocus={e => e.target.style.borderColor = '#60a5fa'}
                  onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.1)'}
                />
              </div>

              {/* Peso */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                <label style={{ fontSize: '11px', fontWeight: 600, color: '#9ca3af' }}>Peso</label>
                <input
                  value={vmForm.peso}
                  onChange={e => setVmForm(f => ({ ...f, peso: e.target.value }))}
                  placeholder="126kg"
                  style={{
                    padding: '8px 12px', borderRadius: '8px', fontSize: '13px',
                    background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                    color: '#fff', outline: 'none',
                  }}
                  onFocus={e => e.target.style.borderColor = '#60a5fa'}
                  onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.1)'}
                />
              </div>

              {/* Vueltas de Aire */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                <label style={{ fontSize: '11px', fontWeight: 600, color: '#9ca3af' }}>Vueltas de Aire</label>
                <input
                  value={vmForm.vueltas_aire}
                  onChange={e => setVmForm(f => ({ ...f, vueltas_aire: e.target.value }))}
                  placeholder="Ej: 2.5"
                  style={{
                    padding: '8px 12px', borderRadius: '8px', fontSize: '13px',
                    background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                    color: '#fff', outline: 'none',
                  }}
                  onFocus={e => e.target.style.borderColor = '#60a5fa'}
                  onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.1)'}
                />
              </div>

              {/* Posición Cortina */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                <label style={{ fontSize: '11px', fontWeight: 600, color: '#9ca3af' }}>Posición Cortina</label>
                <input
                  value={vmForm.posicion_cortina}
                  onChange={e => setVmForm(f => ({ ...f, posicion_cortina: e.target.value }))}
                  placeholder="Ej: 3/4"
                  style={{
                    padding: '8px 12px', borderRadius: '8px', fontSize: '13px',
                    background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                    color: '#fff', outline: 'none',
                  }}
                  onFocus={e => e.target.style.borderColor = '#60a5fa'}
                  onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.1)'}
                />
              </div>

              {/* Sistemas de Control */}
              <div style={{ gridColumn: '1 / -1', display: 'flex', flexDirection: 'column', gap: '5px' }}>
                <label style={{ fontSize: '11px', fontWeight: 600, color: '#9ca3af' }}>Sistemas de Control</label>
                <input
                  value={vmForm.sistemas_control}
                  onChange={e => setVmForm(f => ({ ...f, sistemas_control: e.target.value }))}
                  placeholder="CATALIZADOR / CANISTER"
                  style={{
                    padding: '8px 12px', borderRadius: '8px', fontSize: '13px',
                    background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                    color: '#fff', outline: 'none',
                  }}
                  onFocus={e => e.target.style.borderColor = '#60a5fa'}
                  onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.1)'}
                />
              </div>

              {/* Combustible */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                <label style={{ fontSize: '11px', fontWeight: 600, color: '#9ca3af' }}>Combustible</label>
                <select
                  value={vmForm.combustible}
                  onChange={e => setVmForm(f => ({ ...f, combustible: e.target.value }))}
                  style={{
                    padding: '8px 12px', borderRadius: '8px', fontSize: '13px',
                    background: '#1a1a24', border: '1px solid rgba(255,255,255,0.1)',
                    color: '#fff', outline: 'none',
                  }}
                >
                  <option value="CARBURADOR">CARBURADOR</option>
                  <option value="INYECCION">INYECCION</option>
                </select>
              </div>

              {/* Dimensiones */}
              {[
                ['largo_total', 'Largo Total (mm)'],
                ['ancho_total', 'Ancho Total (mm)'],
                ['altura_total', 'Altura Total (mm)'],
                ['altura_silla', 'Altura de la Silla (mm)'],
                ['distancia_suelo', 'Distancia al Suelo (mm)'],
                ['distancia_ejes', 'Distancia entre Ejes (mm)'],
                ['tanque_combustible', 'Tanque de Combustible (Gal)'],
                ['relacion_compresion', 'Relación de Compresión'],
                ['llanta_delantera', 'Llanta Delantera'],
                ['llanta_trasera', 'Llanta Trasera'],
              ].map(([field, label]) => (
                <div key={field} style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  <label style={{ fontSize: '11px', fontWeight: 600, color: '#9ca3af' }}>{label}</label>
                  <input
                    value={vmForm[field]}
                    onChange={e => setVmForm(f => ({ ...f, [field]: e.target.value }))}
                    style={{
                      padding: '8px 12px', borderRadius: '8px', fontSize: '13px',
                      background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                      color: '#fff', outline: 'none',
                    }}
                    onFocus={e => e.target.style.borderColor = '#60a5fa'}
                    onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.1)'}
                  />
                </div>
              ))}

            </div>

            {/* Error */}
            {vmError && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)',
                borderRadius: '8px', padding: '10px 14px',
              }}>
                <AlertCircle size={14} style={{ color: '#f87171', flexShrink: 0 }} />
                <span style={{ color: '#f87171', fontSize: '12px' }}>{vmError}</span>
              </div>
            )}

            {/* Acciones */}
            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setShowVMModal(false)}
                style={{
                  padding: '8px 18px', borderRadius: '8px',
                  border: '1px solid rgba(255,255,255,0.08)',
                  background: 'transparent', color: '#606075',
                  cursor: 'pointer', fontSize: '12px', fontWeight: 600,
                }}
              >
                Cancelar
              </button>
              <button
                onClick={saveVehicleModel}
                disabled={vmSaving}
                style={{
                  padding: '8px 22px', borderRadius: '8px', border: 'none',
                  background: vmSaving ? 'rgba(96,165,250,0.3)' : '#60a5fa',
                  color: '#fff', cursor: vmSaving ? 'not-allowed' : 'pointer',
                  fontSize: '12px', fontWeight: 700,
                  display: 'flex', alignItems: 'center', gap: '6px',
                }}
              >
                <Save size={13} />
                {vmSaving ? 'Guardando...' : editingVM ? 'Guardar Cambios' : 'Crear Modelo'}
              </button>
            </div>
          </div>
        </div>
      )}

      <style jsx global>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        select option { background: #0c0c0e; color: #fff; }
      `}</style>
    </AdminLayout>
  );
}

const catLabel = {
  display: 'block', fontSize: '0.62rem', fontWeight: 700, color: '#606075',
  textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.4rem',
};
const catInput = {
  width: '100%', padding: '0.6rem 0.875rem',
  background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: '8px', color: '#fff', fontSize: '0.78rem', outline: 'none', boxSizing: 'border-box',
};
