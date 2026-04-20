'use client';

import { useState, useEffect, useCallback } from 'react';
import AdminLayout from '../admin-layout';
import { UploadCloud, Image as ImageIcon, Save, Trash2, Clock, Bike, Plus, Pencil, X, AlertCircle } from 'lucide-react';
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
      <header className="page-header mb-8 flex justify-between items-end border-b border-white/5 pb-6">
        <div>
          <h1 className="page-title">Configuración del <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Sistema</span></h1>
          <p className="text-muted text-sm tracking-wide mt-1">
            Personalización visual y parametrización de variables del sistema
          </p>
        </div>
      </header>

      <div className="max-w-4xl mx-auto space-y-8">
        
        {/* Sección: Identidad Visual */}
        <section className="glass p-6">
          <div className="flex items-center space-x-3 mb-6 border-b border-white/5 pb-4">
            <ImageIcon size={20} className="text-orange-500" />
            <h2 className="text-lg font-bold">Identidad Visual de la Plataforma</h2>
          </div>

          <div className="grid md:grid-cols-2 gap-8 items-start">
            
            {/* Control de subida */}
            <div className="space-y-4">
              <p className="text-sm text-muted">
                Carga el logotipo de la empresa. Este reemplazará el sello estático "UM" en el menú de navegación lateral.
                Se recomienda usar formato PNG con fondo transparente con un ratio preferiblemente horizontal o cuadrado.
              </p>

              <label 
                className="btn flex items-center justify-center space-x-2 w-full transition-all"
                style={{
                  padding: '1rem',
                  border: '1px dashed rgba(255, 255, 255, 0.2)',
                  borderRadius: '1rem',
                  cursor: 'pointer',
                  backgroundColor: 'rgba(255, 255, 255, 0.02)'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = '#ff5f33';
                  e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.05)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.2)';
                  e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.02)';
                }}
              >
                <UploadCloud size={18} />
                <span>Seleccionar nueva imagen</span>
                <input 
                  type="file" 
                  style={{ display: 'none' }}
                  accept="image/png, image/jpeg, image/svg+xml, image/webp" 
                  onChange={handleLogoUpload}
                />
              </label>

              <div className="flex space-x-3 pt-4">
                <button 
                  className="btn-primary flex-1 flex justify-center items-center space-x-2" 
                  onClick={handleSaveLogo}
                  disabled={!logoBase64}
                >
                  <Save size={16} />
                  <span>Guardar Cambios</span>
                </button>
                <button 
                  className="btn flex-1 flex justify-center items-center space-x-2" 
                  onClick={handleRemoveLogo}
                  disabled={!logoBase64}
                  style={{ borderColor: 'rgba(239, 68, 68, 0.2)', color: '#ef4444' }}
                  onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.2)'}
                  onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.05)'}
                >
                  <Trash2 size={16} />
                  <span>Restaurar Default</span>
                </button>
              </div>

              {successMsg && (
                <div className="p-3 bg-green-500/10 border border-green-500/20 text-green-400 text-sm rounded-lg">
                  {successMsg}
                </div>
              )}
            </div>

            {/* Preview visual */}
            <div className="bg-black/40 rounded-2xl p-6 border border-white/5 flex flex-col items-center justify-center min-h-[200px]">
              <h3 className="text-xs uppercase tracking-widest text-muted mb-4 w-full text-left">Vista Previa</h3>
              
              {logoBase64 ? (
                <img 
                  src={logoBase64} 
                  alt="Vista previa del logo" 
                  className="max-h-[120px] max-w-[200px] object-contain drop-shadow-2xl" 
                />
              ) : (
                <div className="flex items-center space-x-3 opacity-50 grayscale">
                  <div className="w-11 h-11 bg-orange-500 rounded-2xl flex items-center justify-center shadow-xl shadow-orange-500/20" style={{ boxShadow: '0 10px 30px rgba(255, 95, 51, 0.3)' }}>
                     <span className="text-white font-black text-xl italic" style={{ transform: 'skewX(-10deg)' }}>UM</span>
                  </div>
                  <div>
                    <h1 className="text-lg font-black tracking-tighter text-white uppercase" style={{ lineHeight: '1' }}>MASTER-DATA</h1>
                    <p className="text-[9px] font-black uppercase tracking-widest text-orange-500">
                      WorkShop Terminal
                    </p>
                  </div>
                </div>
              )}

              <p className="text-[10px] text-muted mt-6 text-center">
                El logo será escalado automáticamente para encajar en el menú lateral.
              </p>
            </div>

          </div>
        </section>

        {/* Sección: Variables del Sistema */}
        <section className="glass p-6">
          <div className="flex items-center space-x-3 mb-6 border-b border-white/5 pb-4">
            <Clock size={20} className="text-orange-500" />
            <h2 className="text-lg font-bold">Variables del Sistema</h2>
          </div>

          <div className="space-y-6">
            {/* Recordatorio de diagnóstico */}
            <div className="space-y-2">
              <label className="block text-sm font-semibold text-white">
                Tiempo de recordatorio de diagnóstico (minutos)
              </label>
              <p className="text-xs text-muted">
                Cuando un técnico arranca con una moto, Sonia esperará este tiempo antes de preguntarle qué encontró.
                Si no responde, le vuelve a preguntar cada vez que se cumpla el intervalo. Mínimo: 5 minutos.
              </p>
              <div className="flex items-center space-x-3 pt-1">
                <input
                  type="number"
                  min={5}
                  max={480}
                  value={reminderMinutes}
                  onChange={e => setReminderMinutes(Number(e.target.value))}
                  className="w-28 px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm focus:outline-none focus:border-orange-500"
                />
                <span className="text-sm text-muted">minutos</span>
                <button
                  className="btn-primary flex items-center space-x-2 px-4 py-2"
                  onClick={handleSaveReminder}
                  disabled={reminderSaving}
                >
                  <Save size={14} />
                  <span>{reminderSaving ? 'Guardando...' : 'Guardar'}</span>
                </button>
              </div>
              {reminderMsg && (
                <p className="text-xs mt-1 text-green-400">{reminderMsg}</p>
              )}
            </div>
          </div>
        </section>

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
    </AdminLayout>
  );
}
