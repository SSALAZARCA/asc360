import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X, Copy, Check, Info, ArrowRight, Activity, User, AlertCircle, Wrench } from 'lucide-react';

export default function SoftwayHelperModal({ detail, order, onClose }) {
  const [activeStep, setActiveStep] = useState(1);
  const [copiedField, setCopiedField] = useState(null);

  // Escuchar Teclado
  useEffect(() => {
    const fn = e => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', fn);
    return () => window.removeEventListener('keydown', fn);
  }, [onClose]);

  if (!detail || !order) return null;

  // Utilidades para formatear info
  const copyToClip = (text, fieldName) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedField(fieldName);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const fmtDateSoftway = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;
  };

  const splitName = (fullName) => {
    if (!fullName) return { first: '', last: '' };
    const parts = fullName.trim().split(' ');
    if (parts.length === 1) return { first: parts[0], last: '' };
    return { first: parts[0], last: parts.slice(1).join(' ') };
  };

  const customerName = splitName(detail?.cliente?.nombre);
  
  const isWarranty = order.tipo_trabajo === 'warranty';
  const isReview = order.tipo_trabajo === 'km_review';
  const isPdi = order.tipo_trabajo === 'pdi';

  // Configuración de Etapas según el Tipo de Servicio
  let steps = [];

  if (isWarranty) {
    steps = [
      {
        title: 'Datos Intervención',
        icon: Activity,
        fields: [
          { label: 'Tipo de Garantía', value: 'Normal', type: 'select', hint: 'Selecciona "Normal" u otra opción' },
          { label: 'Fecha Intervención', value: fmtDateSoftway(detail?.created_at), type: 'input' },
          { label: 'Descripción Avería', value: detail?.recepcion?.customer_notes || 'Fallo reportado por el cliente', type: 'textarea' },
          { label: 'KM', value: detail?.recepcion?.mileage_km || '0', type: 'input' },
          { label: 'Dirección de Entrega', value: detail?.centro?.nombre || '', type: 'select' }
        ]
      },
      {
        title: 'Datos Propietario',
        icon: User,
        fields: [
          { label: 'Apellido', value: customerName.last, type: 'input' },
          { label: 'Nombre', value: customerName.first, type: 'input' },
          { label: 'Dirección', value: detail?.cliente?.direccion || 'No registrada', type: 'input' },
          { label: 'Localidad', value: detail?.cliente?.ciudad || detail?.centro?.ciudad || '', type: 'input' },
          { label: 'C.P.', value: '', type: 'input', hint: 'Dejar vacío si no se requiere' },
          { label: 'Provincia', value: detail?.centro?.ciudad || '', type: 'input' },
          { label: 'País', value: 'Colombia (COL)', type: 'select' },
          { label: 'Teléfono', value: '', type: 'input' },
          { label: 'Móvil', value: detail?.cliente?.telefono || '', type: 'input' },
          { label: 'Correo Electrónico', value: detail?.cliente?.email || 'no-email@umcolombia.co', type: 'input' },
        ]
      },
      {
        title: 'Datos Defecto',
        icon: AlertCircle,
        fields: [
          { label: 'Cód. Problema', value: '', type: 'select', hint: `Seleccionar manualmente en Softway basado en avería: ${detail?.recepcion?.customer_notes?.substring(0, 30) || ''}...` }
        ]
      },
      {
        title: 'Datos Mano de Obra',
        icon: Wrench,
        fields: [
          { label: 'Modelo', value: detail?.vehiculo?.modelo || '', type: 'select', hint: `Busca el modelo: ${detail?.vehiculo?.modelo}` },
          { label: 'Operación', value: '', type: 'select', hint: 'Seleccionar manualmente en Softway' },
          { label: 'Mano de Obra (Horas)', value: '1.0', type: 'input', hint: 'Reemplazar por horas reales autorizadas' }
        ]
      }
    ];
  } else if (isReview) {
    steps = [
      {
        title: 'Datos Revisión',
        icon: Activity,
        fields: [
          { label: 'Tipo de Intervención', value: '', type: 'select', hint: 'Seleccionar manual: (Ej: Otro mantenimiento, Revisión periódica)' },
          { label: 'Fecha Intervención', value: fmtDateSoftway(detail?.created_at), type: 'input' },
          { label: 'Descripción', value: detail?.recepcion?.technician_notes || detail?.recepcion?.customer_notes || 'Revisión preventiva de mantenimiento.', type: 'textarea' },
          { label: 'Kilometraje', value: detail?.recepcion?.mileage_km || '0', type: 'input' },
          { label: 'Número Revisión', value: '1', type: 'input', hint: 'Ajustar si es revisión #2, #3, etc.' }
        ]
      }
    ];
  } else if (isPdi) {
    steps = [
      {
        title: 'Datos Activación',
        icon: Activity,
        fields: [
          { label: 'Matrícula', value: detail?.vehiculo?.placa || '', type: 'input' },
          { label: 'Fecha Matriculación', value: fmtDateSoftway(detail?.created_at), type: 'input', hint: 'Usar fecha de venta/entrega' },
          { label: 'Tipo de Activación', value: 'Nueva activación', type: 'select' }
        ]
      },
      {
        title: 'Datos Propietario',
        icon: User,
        fields: [
          { label: 'Género', value: 'Masculino', type: 'select', hint: 'Ajustar manualmente en Softway' },
          { label: 'Apellido', value: customerName.last, type: 'input' },
          { label: 'Nombre', value: customerName.first, type: 'input' },
          { label: 'Fecha Nacimiento', value: '', type: 'input', hint: 'Dejar vacío si es opcional' },
          { label: 'Dirección', value: detail?.cliente?.direccion || 'No registrada', type: 'input' },
          { label: 'Localidad', value: detail?.cliente?.ciudad || detail?.centro?.ciudad || '', type: 'input' },
          { label: 'C.P.', value: '', type: 'input' },
          { label: 'Provincia', value: detail?.centro?.ciudad || '', type: 'input' },
          { label: 'País', value: 'Colombia (COL)', type: 'select' },
          { label: 'Teléfono', value: '', type: 'input' },
          { label: 'Móvil', value: detail?.cliente?.telefono || '', type: 'input' },
          { label: 'Correo Electrónico', value: detail?.cliente?.email || 'no-email@umcolombia.co', type: 'input' },
        ]
      }
    ];
  } else {
    // Fallback genérico si alguien lo abre por error
    steps = [
      {
        title: 'Información General',
        icon: Info,
        fields: [
          { label: 'Servicio no configurado para autollenado', value: '', type: 'input' }
        ]
      }
    ];
  }

  const activeData = steps[activeStep - 1];
  const ActiveIcon = activeData?.icon || Activity;

  const content = (
    <div className="s-backdrop" onClick={onClose}>
      <div className="s-box" onClick={e => e.stopPropagation()}>
        
        {/* Header Asistente */}
        <div className="s-head">
          <div className="s-head-txt">
            <h2 className="s-title">⚡ Asistente Autollenado Softway</h2>
            <p className="s-subtitle">
              {isWarranty ? 'GARANTÍA' : (isReview ? 'REVISIÓN' : 'ACTIVACIÓN (ALISTAMIENTO)')} — 
              Vehículo: <strong>{detail?.vehiculo?.modelo}</strong> — Bastidor: <strong>{detail?.vehiculo?.vin}</strong>
            </p>
          </div>
          <button className="s-close" onClick={onClose}><X size={15} /></button>
        </div>

        {/* Cuerpop Dividido en Menu Lateral Izquierdo y Contenedor Derecho */}
        <div className="s-layout">
          
          {/* Menu de Pasos (Izquierda) */}
          <div className="s-sidebar">
            <h3 className="s-sidebar-title">Etapas Softway</h3>
            <div className="s-steps">
              {steps.map((s, i) => {
                const stepNum = i + 1;
                const isActive = activeStep === stepNum;
                const StepIcon = s.icon;
                return (
                  <button 
                    key={stepNum} 
                    className={`s-step-btn ${isActive ? 'active' : ''}`}
                    onClick={() => setActiveStep(stepNum)}
                  >
                    <div className="s-step-num">{stepNum}</div>
                    <span className="s-step-name">{s.title}</span>
                    <StepIcon size={14} className="s-step-icon" />
                  </button>
                );
              })}
            </div>
          </div>

          {/* Area Activa (Derecha) */}
          <div className="s-content">
            <div className="s-content-head">
              <ActiveIcon size={20} className="text-blue-500" />
              <h3>{activeStep}. {activeData?.title}</h3>
            </div>

            <div className="s-fields">
              {activeData?.fields.map((f, i) => (
                <div key={i} className="s-field-row">
                  <div className="s-field-info">
                    <span className="s-field-label">{f.label}</span>
                    {f.type === 'select' && <span className="s-badge-sel">Selector Softway</span>}
                  </div>
                  
                  <div className="s-field-action">
                    {f.value ? (
                      <div className="s-copy-box">
                        <span className={`s-copy-val ${f.type==='textarea' ? 's-textarea' : ''}`}>{f.value}</span>
                        <button 
                          className={`s-copy-btn ${copiedField === f.label ? 'copied' : ''}`}
                          onClick={() => copyToClip(f.value, f.label)}
                          title="Copiar al portapapeles"
                        >
                          {copiedField === f.label ? (
                            <><Check size={14} /> <span>Copiado</span></>
                          ) : (
                            <><Copy size={14} /> <span>Copiar</span></>
                          )}
                        </button>
                      </div>
                    ) : (
                      <span className="s-field-empty">Selección / Ingreso Manual</span>
                    )}
                    
                    {f.hint && (
                      <div className="s-field-hint">
                        <Info size={11} /> {f.hint}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <div className="s-footer-nav">
              {activeStep > 1 && (
                <button className="s-nav-btn outline" onClick={() => setActiveStep(activeStep - 1)}>
                  Atrás
                </button>
              )}
              {activeStep < steps.length ? (
                <button className="s-nav-btn primary" onClick={() => setActiveStep(activeStep + 1)}>
                  Siguiente Etapa <ArrowRight size={14} />
                </button>
              ) : (
                <button className="s-nav-btn success" onClick={onClose}>
                  <Check size={14} /> Terminar Carga en Softway
                </button>
              )}
            </div>
          </div>

        </div>

      </div>

      <style jsx>{`
        .s-backdrop {
          position: fixed; inset: 0; background: rgba(0,0,0,0.8);
          backdrop-filter: blur(5px); z-index: 99999;
          display: flex; align-items: center; justify-content: center;
          padding: 2rem; animation: sMin 0.2s ease;
        }
        @keyframes sMin { from { opacity: 0; } to { opacity: 1; } }

        .s-box {
          background: #111114; border: 1px solid rgba(59,130,246,0.3);
          border-radius: 16px; width: 100%; max-width: 900px; max-height: 85vh;
          display: flex; flex-direction: column; box-shadow: 0 32px 64px rgba(0,0,0,0.8);
          overflow: hidden;
        }

        .s-head {
          display: flex; justify-content: space-between; align-items: flex-start;
          padding: 1.25rem 1.5rem; background: linear-gradient(180deg, rgba(59,130,246,0.1) 0%, transparent 100%);
          border-bottom: 1px solid rgba(255,255,255,0.06);
        }
        .s-title { font-size: 1.2rem; font-weight: 900; color: #fff; margin: 0; display:flex; align-items:center; gap:0.5rem; text-transform:uppercase; letter-spacing:0.04em; }
        .s-subtitle { font-size: 0.75rem; color: rgba(255,255,255,0.5); margin: 0.2rem 0 0; }
        .s-close { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); width: 32px; height: 32px; border-radius: 8px; color: rgba(255,255,255,0.6); display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.2s; }
        .s-close:hover { background: rgba(239,68,68,0.2); color: #ef4444; border-color: rgba(239,68,68,0.4); transform: rotate(90deg); }

        .s-layout { display: flex; flex: 1; overflow: hidden; }

        /* Sidebar (Left) */
        .s-sidebar { width: 220px; border-right: 1px solid rgba(255,255,255,0.06); background: rgba(0,0,0,0.4); padding: 1.25rem; display: flex; flex-direction: column; overflow-y: auto; }
        .s-sidebar-title { font-size: 0.65rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.1em; color: rgba(255,255,255,0.3); margin: 0 0 1rem 0; }
        .s-steps { display: flex; flex-direction: column; gap: 0.6rem; }
        .s-step-btn { display: flex; align-items: center; gap: 0.5rem; background: transparent; border: none; padding: 0.5rem 0.2rem; cursor: pointer; color: rgba(255,255,255,0.4); border-left: 2px solid transparent; transition: all 0.2s; text-align: left; }
        .s-step-btn:hover { color: rgba(255,255,255,0.8); }
        .s-step-btn.active { color: white; border-left-color: #3b82f6; padding-left: 0.5rem; }
        
        .s-step-num { width: 22px; height: 22px; border-radius: 50%; background: rgba(255,255,255,0.05); display: flex; align-items: center; justify-content: center; font-size: 0.65rem; font-weight: 900; }
        .s-step-btn.active .s-step-num { background: #3b82f6; color: white; box-shadow: 0 0 10px rgba(59,130,246,0.5); }
        .s-step-name { flex: 1; font-size: 0.75rem; font-weight: 700; }
        .s-step-icon { opacity: 0; transition: opacity 0.2s; }
        .s-step-btn.active .s-step-icon { opacity: 1; color: #60a5fa; }

        /* Content Area (Right) */
        .s-content { flex: 1; display: flex; flex-direction: column; background: rgba(255,255,255,0.01); overflow-y: auto; }
        .s-content-head { padding: 1.5rem; border-bottom: 1px solid rgba(255,255,255,0.04); display: flex; align-items: center; gap: 0.6rem; }
        .s-content-head h3 { font-size: 1.1rem; font-weight: 800; margin: 0; color: white; }

        .s-fields { padding: 1.5rem; display: flex; flex-direction: column; gap: 1.2rem; flex: 1; }
        .s-field-row { display: flex; flex-direction: column; gap: 0.5rem; }
        .s-field-info { display: flex; align-items: center; justify-content: space-between; }
        .s-field-label { font-size: 0.7rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; color: rgba(255,255,255,0.5); }
        .s-badge-sel { font-size: 0.55rem; font-weight: 700; background: rgba(245,158,11,0.15); color: #f59e0b; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; border: 1px solid rgba(245,158,11,0.3); }

        .s-field-action { display: flex; flex-direction: column; gap: 0.4rem; }
        .s-copy-box { display: flex; gap: 0.5rem; align-items: stretch; background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; overflow: hidden; }
        .s-copy-val { flex: 1; padding: 0.8rem 1rem; font-size: 0.85rem; font-weight: 600; color: white; }
        .s-textarea { white-space: pre-wrap; word-break: break-word; font-size: 0.8rem; line-height: 1.5; color: rgba(255,255,255,0.85); font-style: italic; }
        
        .s-copy-btn { border: none; background: rgba(59,130,246,0.1); color: #60a5fa; cursor: pointer; padding: 0 1rem; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.3rem; transition: all 0.2s; font-size: 0.6rem; font-weight: 800; text-transform: uppercase; border-left: 1px solid rgba(255,255,255,0.05); min-width: 80px; }
        .s-copy-btn:hover { background: rgba(59,130,246,0.25); color: white; }
        .s-copy-btn.copied { background: rgba(16,185,129,0.2); color: #10b981; pointer-events: none; }

        .s-field-empty { font-size: 0.75rem; color: rgba(255,255,255,0.2); font-style: italic; padding: 0.8rem 1rem; background: rgba(0,0,0,0.2); border-radius: 8px; border: 1px dashed rgba(255,255,255,0.1); }
        .s-field-hint { display: flex; align-items: flex-start; gap: 0.4rem; font-size: 0.65rem; color: rgba(255,255,255,0.4); line-height: 1.4; padding: 0 0.5rem; }

        /* Footer Nav */
        .s-footer-nav { padding: 1.5rem; border-top: 1px solid rgba(255,255,255,0.04); display: flex; justify-content: flex-end; gap: 0.8rem; background: rgba(0,0,0,0.2); }
        .s-nav-btn { display: flex; align-items: center; gap: 0.5rem; padding: 0.6rem 1.25rem; border-radius: 8px; font-size: 0.75rem; font-weight: 800; text-transform: uppercase; cursor: pointer; transition: all 0.2s; outline: none; border: none; letter-spacing: 0.05em; }
        .s-nav-btn.outline { background: transparent; border: 1px solid rgba(255,255,255,0.2); color: rgba(255,255,255,0.6); }
        .s-nav-btn.outline:hover { background: rgba(255,255,255,0.05); color: white; }
        .s-nav-btn.primary { background: #3b82f6; color: white; box-shadow: 0 4px 15px rgba(59,130,246,0.3); }
        .s-nav-btn.primary:hover { background: #2563eb; transform: translateY(-2px); box-shadow: 0 6px 20px rgba(59,130,246,0.4); }
        .s-nav-btn.success { background: #10b981; color: white; box-shadow: 0 4px 15px rgba(16,185,129,0.3); }
        .s-nav-btn.success:hover { background: #059669; transform: translateY(-2px); box-shadow: 0 6px 20px rgba(16,185,129,0.4); }

      `}</style>
    </div>
  );

  return typeof window !== 'undefined' ? createPortal(content, document.body) : null;
}
