'use client';
/**
 * frontend/components/motored/maestros/ClientesTecniredTab.js
 *
 * Lista de NIT de clientes Tecnired (feature motored-tablero-asesores, T2).
 * Solo lectura: la lista se cambia subiendo un archivo con "Cargar lista", y
 * cada carga REEMPLAZA la lista completa (por eso el aviso). Alimenta el
 * indicador de ventas a clientes Tecnired del tablero de asesores; no tiene
 * ninguna relación con el motor de pedidos.
 */
import { useEffect, useState } from 'react';
import MotoredTableScroll from '../MotoredTableScroll';
import { listClientesTecnired } from '../../../lib/motored/api';
import BulkUploadModal from './BulkUploadModal';

const PAGE_SIZE = 50;
const mutedStyle = { fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' };

function useClientesTecnired() {
  const [pagina, setPagina] = useState({ items: [], total: 0 });
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async (nextPage, nextQ) => {
    setLoading(true);
    setError('');
    try {
      setPagina(await listClientesTecnired({ page: nextPage, pageSize: PAGE_SIZE, q: nextQ }));
    } catch (err) {
      setError(err.message || 'Error al cargar los clientes Tecnired');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(1, '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const buscar = (texto) => {
    setQ(texto);
    setPage(1);
    return load(1, texto);
  };
  const irA = (nextPage) => {
    setPage(nextPage);
    return load(nextPage, q);
  };
  const recargar = () => buscar(q);

  return { pagina, page, loading, error, buscar, irA, recargar };
}

function Encabezado({ onOpenBulk }) {
  return (
    <div
      style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem',
        padding: '0.85rem 1rem', background: 'var(--motored-surface-alt, #f4f4f5)',
        border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: 'var(--motored-radius-md, 8px)',
      }}
    >
      <div>
        <h2 className="motored-h-seccion">Clientes Tecnired</h2>
        <p style={{ ...mutedStyle, margin: '0.2rem 0 0' }}>
          Lista de NIT de los clientes Tecnired. Cada carga reemplaza la lista completa: lo que no esté en el archivo se borra.
        </p>
      </div>
      <button type="button" className="motored-btn motored-btn-secondary" onClick={onOpenBulk}>
        Cargar lista
      </button>
    </div>
  );
}

function Buscador({ onBuscar }) {
  const [texto, setTexto] = useState('');
  return (
    <form
      role="search"
      onSubmit={(e) => { e.preventDefault(); onBuscar(texto.trim()); }}
      style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}
    >
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Buscar por NIT o razón social
        <input type="text" value={texto} onChange={(e) => setTexto(e.target.value)} />
      </label>
      <button type="submit" className="motored-btn motored-btn-secondary">Buscar</button>
    </form>
  );
}

function Tabla({ items }) {
  return (
    <MotoredTableScroll>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
            <th style={{ padding: '0 12px 8px 0' }}>NIT</th>
            <th style={{ padding: '0 12px 8px 0' }}>Razón social</th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
              <td style={{ padding: '10px 12px 10px 0' }}>{c.nit}</td>
              <td style={{ padding: '10px 12px 10px 0' }}>{c.razon_social || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}

function Paginador({ page, total, onPage }) {
  const paginas = Math.max(1, Math.ceil(total / PAGE_SIZE));
  return (
    <nav aria-label="Paginación de clientes Tecnired" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
      <button type="button" className="motored-btn motored-btn-secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Anterior
      </button>
      <span style={mutedStyle}>Página {page} de {paginas}</span>
      <button type="button" className="motored-btn motored-btn-secondary" disabled={page >= paginas} onClick={() => onPage(page + 1)}>
        Siguiente
      </button>
      <span style={mutedStyle}>{total} clientes</span>
    </nav>
  );
}

export default function ClientesTecniredTab() {
  const { pagina, page, loading, error, buscar, irA, recargar } = useClientesTecnired();
  const [showBulk, setShowBulk] = useState(false);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <Encabezado onOpenBulk={() => setShowBulk(true)} />

      {error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>}

      <Buscador onBuscar={buscar} />

      {loading ? (
        <p style={{ ...mutedStyle, fontSize: '0.8rem' }}>Cargando...</p>
      ) : (
        <>
          <Tabla items={pagina.items} />
          <Paginador page={page} total={pagina.total} onPage={irA} />
        </>
      )}

      {showBulk && (
        <BulkUploadModal
          entidad="cliente_tecnired"
          onClose={() => setShowBulk(false)}
          onSuccess={() => {
            setShowBulk(false);
            recargar();
          }}
        />
      )}
    </div>
  );
}
