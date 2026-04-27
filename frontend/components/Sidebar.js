'use client';
import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';

const API_URL = () => (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace(/^http:\/\/(?!localhost)/, 'https://');
import {
  BarChart4,
  Wrench,
  Users,
  Building2,
  LogOut,
  LayoutDashboard,
  Settings,
  Ship,
  BookOpen,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

const ALL_ITEMS = [
  { id: 'dashboard', name: 'Centro de Comando', icon: BarChart4, path: '/', adminOnly: true, allowAdministrativo: true },
  { id: 'kanban', name: 'Tablero Operativo', icon: LayoutDashboard, path: '/kanban' },
  { id: 'services', name: 'Gestión de Órdenes', icon: Wrench, path: '/services' },
  { id: 'imports', name: 'Estado Pedidos', icon: Ship, path: '/imports', importsOnly: true },
  { id: 'tenants', name: 'Red de Talleres', icon: Building2, path: '/tenants', adminOnly: true },
  { id: 'users', name: 'Personal & Acceso', icon: Users, path: '/users', adminOnly: true },
  { id: 'parts-catalog', name: 'Catálogo de Partes', icon: BookOpen, path: '/parts-catalog', adminOnly: true },
  { id: 'settings', name: 'Configuración', icon: Settings, path: '/settings', adminOnly: true },
];

export default function Sidebar({ collapsed = false, onToggle }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState(null);
  const [companyLogo, setCompanyLogo] = useState(null);
  const [showPwdModal, setShowPwdModal] = useState(false);
  const [pwdForm, setPwdForm] = useState({ current: '', next: '' });
  const [pwdError, setPwdError] = useState('');
  const [pwdLoading, setPwdLoading] = useState(false);

  useEffect(() => {
    const checkAuth = () => {
      const stored = sessionStorage.getItem('um_user');
      if (stored) setUser(JSON.parse(stored));
      const cached = localStorage.getItem('um_logo');
      setCompanyLogo(cached || null);
    };
    checkAuth();
    window.addEventListener('storage', checkAuth);

    // Logo global de la marca — sin asociación a taller
    fetch(`${API_URL()}/settings/logo`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.logo_base64) {
          setCompanyLogo(data.logo_base64);
          localStorage.setItem('um_logo', data.logo_base64);
        } else {
          setCompanyLogo(null);
          localStorage.removeItem('um_logo');
        }
      })
      .catch(() => {});

    return () => window.removeEventListener('storage', checkAuth);
  }, []);

  const handleChangePassword = async () => {
    if (!pwdForm.current || !pwdForm.next) { setPwdError('Completá ambos campos'); return; }
    if (pwdForm.next.length < 6) { setPwdError('Mínimo 6 caracteres'); return; }
    setPwdLoading(true); setPwdError('');
    try {
      const token = sessionStorage.getItem('um_token');
      const res = await fetch(`${API_URL()}/auth/change-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ current_password: pwdForm.current, new_password: pwdForm.next })
      });
      if (res.status === 204) {
        setShowPwdModal(false);
        setPwdForm({ current: '', next: '' });
      } else {
        const data = await res.json();
        setPwdError(data.detail || 'Error al cambiar contraseña');
      }
    } catch { setPwdError('Error de conexión'); }
    finally { setPwdLoading(false); }
  };

  const handleLogout = () => {
    sessionStorage.removeItem('um_user');
    window.dispatchEvent(new Event('storage'));
    router.push('/login');
  };

  const isProveedor = user?.role === 'proveedor';
  const isAdministrativo = user?.role === 'administrativo';

  const menuItems = ALL_ITEMS.filter(item => {
    // proveedor solo ve imports
    if (isProveedor) return !!item.importsOnly;
    // administrativo: dashboard, services e imports — sin adminOnly (tenants/users/settings)
    if (isAdministrativo) {
      if (item.adminOnly && !item.allowAdministrativo) return false;
      if (item.id === 'kanban') return false;
      return true;
    }
    // items exclusivos de imports: superadmin y proveedor
    if (item.importsOnly && user?.role !== 'superadmin') return false;
    // items adminOnly: solo superadmin
    if (item.adminOnly && user?.role !== 'superadmin') return false;
    return true;
  });

  return (
    <aside
      className="fixed left-6 top-6 bottom-6 glass flex flex-col z-50 overflow-hidden"
      style={{ width: collapsed ? '72px' : '280px', transition: 'width 0.25s ease' }}
    >
      {/* Brand Header */}
      <div style={{
        padding: collapsed ? '1.25rem 0' : '2rem 2rem 2.5rem',
        display: 'flex',
        alignItems: 'center',
        justifyContent: collapsed ? 'center' : 'flex-start',
        minHeight: collapsed ? '64px' : 'auto',
        transition: 'padding 0.25s ease',
      }}>
        {!collapsed && (companyLogo ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', height: '4.5rem' }}>
            <img
              src={companyLogo}
              alt="Company Logo"
              style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain', filter: 'drop-shadow(0 10px 15px rgba(0,0,0,0.5))' }}
            />
          </div>
        ) : (
          <div className="flex items-center space-x-3">
            <div className="w-11 h-11 bg-orange-500 rounded-2xl flex items-center justify-center" style={{ boxShadow: '0 10px 30px rgba(255, 95, 51, 0.3)', flexShrink: 0 }}>
              <span className="text-white font-black text-xl italic" style={{ transform: 'skewX(-10deg)', color: '#fff' }}>UM</span>
            </div>
            <div>
              <h1 className="text-lg font-black tracking-tighter text-white uppercase" style={{ lineHeight: '1', color: '#fff' }}>MASTER-DATA</h1>
              <p className="text-[9px] font-black uppercase tracking-widest" style={{ color: '#ff5f33' }}>
                {user?.role === 'superadmin' ? 'Network Admin' : 'WorkShop Terminal'}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Toggle button */}
      <button
        onClick={() => onToggle?.(!collapsed)}
        style={{
          position: 'absolute',
          top: '1.1rem',
          right: '0.6rem',
          background: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: '8px',
          width: '26px',
          height: '26px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          color: 'rgba(255,255,255,0.35)',
          flexShrink: 0,
          transition: 'color 0.2s, background 0.2s',
        }}
        onMouseEnter={e => { e.currentTarget.style.color = '#ff5f33'; e.currentTarget.style.background = 'rgba(255,95,51,0.1)'; }}
        onMouseLeave={e => { e.currentTarget.style.color = 'rgba(255,255,255,0.35)'; e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; }}
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
      </button>

      {/* Main Navigation */}
      <nav style={{ flex: 1, padding: collapsed ? '0 8px' : '0 1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.path;
          return (
            <Link key={item.id} href={item.path} style={{ display: 'block', textDecoration: 'none' }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: collapsed ? 'center' : 'space-between',
                  padding: collapsed ? '0.75rem 0' : '0.875rem 1.25rem',
                  borderRadius: '1rem',
                  color: isActive ? '#fff' : '#606075',
                  backgroundColor: isActive ? 'rgba(255,255,255,0.05)' : 'transparent',
                  transition: 'background 0.2s, color 0.2s',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: collapsed ? 0 : '1rem' }}>
                  <Icon size={18} style={{ strokeWidth: isActive ? '2.5px' : '2px', color: isActive ? '#ff5f33' : 'inherit', flexShrink: 0 }} />
                  {!collapsed && (
                    <span style={{ fontSize: '0.6875rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'inherit' }}>
                      {item.name}
                    </span>
                  )}
                </div>
                {!collapsed && isActive && (
                  <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#ff5f33', boxShadow: '0 0 10px #ff5f33' }} />
                )}
              </div>
            </Link>
          );
        })}
      </nav>

      {/* Bottom Profile */}
      <div style={{ padding: collapsed ? '1rem 8px' : '1rem', marginTop: 'auto' }}>
        <div
          onClick={() => { setPwdForm({ current: '', next: '' }); setPwdError(''); setShowPwdModal(true); }}
          style={{
            padding: collapsed ? '0.75rem 0' : '1rem',
            borderRadius: '1.5rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: collapsed ? 'center' : 'flex-start',
            gap: '0.75rem',
            cursor: 'pointer',
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.05)',
          }}
        >
          <div style={{ width: '2.5rem', height: '2.5rem', borderRadius: '50%', background: '#ff5f33', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, fontSize: '0.75rem', color: '#fff', flexShrink: 0 }}>
            {user ? user.name.substring(0, 2).toUpperCase() : 'UM'}
          </div>
          {!collapsed && (
            <>
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <p style={{ fontSize: '0.6875rem', fontWeight: 900, color: '#fff', textTransform: 'uppercase', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', margin: 0 }}>{user?.name || 'Invitado'}</p>
                <p style={{ fontSize: '0.5625rem', fontWeight: 700, color: '#606075', textTransform: 'uppercase', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', margin: 0 }}>
                  {user?.role === 'superadmin' ? 'Central HQ' : user?.role === 'proveedor' ? 'Proveedor Externo' : (user?.email || 'Taller Local')}
                </p>
              </div>
              <button onClick={(e) => { e.stopPropagation(); handleLogout(); }} style={{ cursor: 'pointer', color: 'rgba(255,255,255,0.4)', background: 'transparent', border: 'none', display: 'flex', alignItems: 'center' }}>
                <LogOut size={16} />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Modal cambio de contraseña */}
      {showPwdModal && (
        <div
          onClick={() => setShowPwdModal(false)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        >
          <div onClick={e => e.stopPropagation()} style={{ background: '#0c0c0e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '16px', padding: '2rem', width: '100%', maxWidth: '360px', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <p style={{ color: '#fff', fontWeight: 900, fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.05em', margin: 0 }}>Cambiar contraseña</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <input
                type="password"
                placeholder="Contraseña actual"
                value={pwdForm.current}
                onChange={e => setPwdForm({ ...pwdForm, current: e.target.value })}
                style={{ background: '#151518', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '10px', padding: '0.75rem 1rem', color: '#fff', fontSize: '0.85rem', outline: 'none' }}
              />
              <input
                type="password"
                placeholder="Nueva contraseña"
                value={pwdForm.next}
                onChange={e => setPwdForm({ ...pwdForm, next: e.target.value })}
                style={{ background: '#151518', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '10px', padding: '0.75rem 1rem', color: '#fff', fontSize: '0.85rem', outline: 'none' }}
              />
            </div>
            {pwdError && <p style={{ color: '#ef4444', fontSize: '0.75rem', margin: 0 }}>{pwdError}</p>}
            <button
              onClick={handleChangePassword}
              disabled={pwdLoading}
              style={{ background: '#ff5f33', color: '#fff', border: 'none', borderRadius: '10px', padding: '0.75rem', fontWeight: 900, fontSize: '0.75rem', textTransform: 'uppercase', cursor: 'pointer', opacity: pwdLoading ? 0.6 : 1 }}
            >
              {pwdLoading ? 'Guardando...' : 'Guardar'}
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}
