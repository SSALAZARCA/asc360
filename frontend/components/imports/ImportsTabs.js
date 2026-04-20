'use client';
import { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../../lib/authFetch';
import ShipmentTable from './ShipmentTable';
import ExcelUploadModal from './ExcelUploadModal';
import OrderDetailModal from './OrderDetailModal';
import SparePartsTab from './SparePartsTab';
import MotocicletasTab from './MotocicletasTab';
import BackorderTab from './BackorderTab';
import DashboardTab from './DashboardTab';
import ShipmentOrderFormModal from './ShipmentOrderFormModal';
import NuevoPedidoModal from './NuevoPedidoModal';
import { RefreshCw, Upload, FileUp, Plus } from 'lucide-react';

const TABS = [
  { id: 'orders', label: 'Pedidos' },
  { id: 'motocicletas', label: 'Motocicletas' },
  { id: 'spare_parts', label: 'Repuestos' },
  { id: 'backorders', label: 'Backorders' },
  { id: 'dashboard', label: 'Dashboard' },
];

function API() {
  return (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace('http://', 'https://');
}

export default function ImportsTabs({ userRole }) {
  const [activeTab, setActiveTab] = useState('orders');

  // --- Estado de la pestaña Pedidos ---
  const [orders, setOrders] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState(null);

  // Filtros
  const [filterCycle, setFilterCycle] = useState('');
  const [filterSP, setFilterSP] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [search, setSearch] = useState('');

  // Modals
  const [showShipmentUpload, setShowShipmentUpload] = useState(false);
  const [showShippingDocUpload, setShowShippingDocUpload] = useState(false);
  const [detailOrder, setDetailOrder] = useState(null);
  const [formModal, setFormModal] = useState({ open: false, order: null }); // edit
  const [showNuevoPedido, setShowNuevoPedido] = useState(false);

  const PAGE_SIZE = 50;

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page, page_size: PAGE_SIZE });
      if (filterCycle) params.append('cycle', filterCycle);
      if (filterSP !== '') params.append('is_spare_part', filterSP);
      if (filterStatus) params.append('computed_status', filterStatus);
      if (search) params.append('search', search);

      const res = await authFetch(`${API()}/imports/shipment-orders?${params}`);
      const data = await res.json();
      setOrders(data.items ?? []);
      setTotal(data.total ?? 0);
    } catch (e) {
      console.error('Error cargando pedidos:', e);
    } finally {
      setLoading(false);
    }
  }, [page, filterCycle, filterSP, filterStatus, search]);

  useEffect(() => {
    if (activeTab === 'orders') fetchOrders();
  }, [activeTab, fetchOrders]);

  const handleDelete = async (id) => {
    try {
      await authFetch(`${API()}/imports/shipment-orders/${id}`, { method: 'DELETE' });
      fetchOrders();
    } catch (e) {
      console.error('Error eliminando pedido:', e);
    }
  };

  const handleUploadSuccess = () => {
    // No cerrar el modal aquí — el usuario necesita ver el resultado.
    // El fetch se hace cuando el usuario cierra el modal manualmente.
    fetchOrders();
  };

  const handleShipmentUploadClose = () => {
    setShowShipmentUpload(false);
    fetchOrders();
  };

  const handleShippingDocUploadClose = () => {
    setShowShippingDocUpload(false);
    fetchOrders();
  };

  const handleFormSuccess = () => {
    setFormModal({ open: false, order: null });
    fetchOrders();
  };

  const handleEdit = (order) => {
    setFormModal({ open: true, order });
  };

  const handleRowClick = async (order) => {
    // Carga el detalle completo (incluye moto_units) antes de abrir el modal
    try {
      const res = await authFetch(`${API()}/imports/shipment-orders/${order.id}`);
      const detail = await res.json();
      setDetailOrder(detail);
    } catch {
      setDetailOrder(order); // fallback con datos parciales
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: '4px', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '0' }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '10px 20px', fontSize: '12px', fontWeight: 700,
              letterSpacing: '0.06em', textTransform: 'uppercase',
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: activeTab === tab.id ? '#ff5f33' : '#606075',
              borderBottom: activeTab === tab.id ? '2px solid #ff5f33' : '2px solid transparent',
              transition: 'all 0.2s',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* --- PESTAÑA PEDIDOS --- */}
      {activeTab === 'orders' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

          {/* Toolbar */}
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
            {/* Búsqueda */}
            <input
              placeholder="Buscar PI o modelo..."
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1); }}
              style={{
                flex: 1, minWidth: 200, padding: '8px 12px', borderRadius: '8px',
                background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)',
                color: '#fff', fontSize: '12px', outline: 'none',
              }}
            />

            {/* Filtro ciclo */}
            <input
              type="number"
              placeholder="Ciclo..."
              value={filterCycle}
              onChange={e => { setFilterCycle(e.target.value); setPage(1); }}
              style={{
                width: 90, padding: '8px 12px', borderRadius: '8px',
                background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)',
                color: '#fff', fontSize: '12px', outline: 'none',
              }}
            />

            {/* Filtro tipo */}
            <select
              value={filterSP}
              onChange={e => { setFilterSP(e.target.value); setPage(1); }}
              style={{
                padding: '8px 12px', borderRadius: '8px',
                background: '#1a1a24', border: '1px solid rgba(255,255,255,0.08)',
                color: filterSP === '' ? '#606075' : '#fff', fontSize: '12px', outline: 'none',
              }}
            >
              <option value="">Todos</option>
              <option value="false">Solo Motos</option>
              <option value="true">Solo Repuestos</option>
            </select>

            {/* Filtro estado */}
            <select
              value={filterStatus}
              onChange={e => { setFilterStatus(e.target.value); setPage(1); }}
              style={{
                padding: '8px 12px', borderRadius: '8px',
                background: '#1a1a24', border: '1px solid rgba(255,255,255,0.08)',
                color: filterStatus === '' ? '#606075' : '#fff', fontSize: '12px', outline: 'none',
              }}
            >
              <option value="">Todos los estados</option>
              <option value="en_preparacion">En Preparación</option>
              <option value="listo_fabrica">Listo Fábrica</option>
              <option value="en_transito">En Tránsito</option>
              <option value="en_destino">En Destino</option>
              <option value="completado">Completado</option>
              <option value="backorder">Backorder</option>
            </select>

            {/* Refresh */}
            <button
              onClick={fetchOrders}
              style={{ padding: '8px', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', cursor: 'pointer', color: '#9ca3af' }}
            >
              <RefreshCw size={14} />
            </button>

            {/* Nuevo Pedido (imports_editor + superadmin) */}
            {(userRole === 'superadmin' || userRole === 'imports_editor') && (
              <button
                onClick={() => setShowNuevoPedido(true)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '6px',
                  padding: '8px 14px', borderRadius: '8px', border: 'none',
                  background: 'rgba(34,197,94,0.15)', color: '#22c55e',
                  fontSize: '11px', fontWeight: 700, cursor: 'pointer',
                  letterSpacing: '0.04em',
                }}
              >
                <Plus size={13} /> Nuevo Pedido
              </button>
            )}

            {/* Botones de importación (solo superadmin) */}
            {userRole === 'superadmin' && (
              <>
                <button
                  onClick={() => setShowShipmentUpload(true)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '6px',
                    padding: '8px 14px', borderRadius: '8px', border: 'none',
                    background: 'rgba(255,95,51,0.15)', color: '#ff5f33',
                    fontSize: '11px', fontWeight: 700, cursor: 'pointer',
                    letterSpacing: '0.04em',
                  }}
                >
                  <Upload size={13} /> Shipment Status
                </button>
                <button
                  onClick={() => setShowShippingDocUpload(true)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '6px',
                    padding: '8px 14px', borderRadius: '8px', border: 'none',
                    background: 'rgba(96,165,250,0.1)', color: '#60a5fa',
                    fontSize: '11px', fontWeight: 700, cursor: 'pointer',
                    letterSpacing: '0.04em',
                  }}
                >
                  <FileUp size={13} /> Packing List Motos
                </button>
              </>
            )}
          </div>

          {/* Contador */}
          <p style={{ margin: 0, fontSize: '11px', color: '#606075' }}>
            {total} pedido{total !== 1 ? 's' : ''} encontrado{total !== 1 ? 's' : ''}
          </p>

          {/* Tabla */}
          <ShipmentTable
            orders={orders}
            total={total}
            page={page}
            pageSize={PAGE_SIZE}
            onPageChange={setPage}
            onRowClick={handleRowClick}
            onEdit={handleEdit}
            onDelete={handleDelete}
            userRole={userRole}
            loading={loading}
          />
        </div>
      )}

      {/* --- PESTAÑAS FUTURAS --- */}
      {activeTab === 'motocicletas' && (
        <MotocicletasTab userRole={userRole} />
      )}
      {activeTab === 'spare_parts' && (
        <SparePartsTab userRole={userRole} />
      )}
      {activeTab === 'backorders' && (
        <BackorderTab userRole={userRole} />
      )}
      {activeTab === 'dashboard' && (
        <DashboardTab />
      )}

      {/* Modal de detalle */}
      {detailOrder && (
        <OrderDetailModal
          order={detailOrder}
          onClose={() => setDetailOrder(null)}
          userRole={userRole}
        />
      )}

      {/* Modal nuevo pedido (SP o Motos desde Excel) */}
      <NuevoPedidoModal
        isOpen={showNuevoPedido}
        onClose={() => setShowNuevoPedido(false)}
        onSuccess={() => { setShowNuevoPedido(false); fetchOrders(); }}
      />

      {/* Modal edit */}
      <ShipmentOrderFormModal
        isOpen={formModal.open}
        order={formModal.order}
        onClose={() => setFormModal({ open: false, order: null })}
        onSuccess={handleFormSuccess}
      />

      {/* Modals de upload */}
      <ExcelUploadModal
        isOpen={showShipmentUpload}
        onClose={handleShipmentUploadClose}
        onSuccess={handleUploadSuccess}
        uploadUrl={`${API()}/imports/shipment-excel`}
        title="Importar Shipment Status"
      />
      <ExcelUploadModal
        isOpen={showShippingDocUpload}
        onClose={handleShippingDocUploadClose}
        onSuccess={handleUploadSuccess}
        uploadUrl={`${API()}/imports/shipping-doc-excel`}
        title="Importar Packing List de Motos (VINs)"
      />
    </div>
  );
}
