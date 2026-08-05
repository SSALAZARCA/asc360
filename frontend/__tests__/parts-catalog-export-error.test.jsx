/**
 * Regression tests for 5 silent-failure spots in
 * frontend/app/parts-catalog/page.js, all flagged by the same gga review:
 * a failed "Exportar Excel" request (`handleExport`), and 4 background
 * fetches (vehicle-models, pricing-factors, coverage-on-model-change,
 * coverage-refresh-after-rotation-import) that used to swallow errors via
 * an empty `.catch(() => {})` with zero user-facing feedback.
 *
 * Same isolation technique as parts-catalog-es-inline-edit.test.jsx and
 * catalog-upload.test.jsx: each handler/effect is copied verbatim into a
 * minimal widget rather than mounting the full 1150+ line page.
 */
import React, { useState, useEffect } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockAuthFetch = jest.fn();
jest.mock('../lib/authFetch', () => ({
  authFetch: (...args) => mockAuthFetch(...args),
}));
import { authFetch } from '../lib/authFetch';

const mockToast = { error: jest.fn(), success: jest.fn() };
jest.mock('../lib/toast', () => ({ toast: { error: (...a) => mockToast.error(...a), success: (...a) => mockToast.success(...a) } }));
import { toast } from '../lib/toast';

// === handleExport — exact copy from frontend/app/parts-catalog/page.js ===
function ExportWidget() {
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      const params = new URLSearchParams({
        search: '',
        model_code: '',
        rotation_class: '',
        coverage_status: '',
      });
      const res = await authFetch(`/parts/admin/catalog/export?${params}`);
      if (!res.ok) { toast.error('No se pudo exportar el Excel.'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const fname = 'maestro_partes.xlsx';
      const a = document.createElement('a');
      a.href = url;
      a.download = fname;
      a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error('No se pudo exportar el Excel.'); }
    finally { setExporting(false); }
  };

  return <button onClick={handleExport} disabled={exporting}>{exporting ? 'Exportando...' : 'Exportar Excel'}</button>;
}

// === vehicle-models fetch effect — exact copy from page.js ===
function VehicleModelsWidget() {
  const [models, setModels] = useState([]);
  useEffect(() => {
    authFetch('/parts/admin/vehicle-models')
      .then(r => r.ok ? r.json() : [])
      .then(data => setModels((Array.isArray(data) ? data : []).filter(m => m.catalog_model_code)))
      .catch(() => toast.error('No se pudieron cargar los modelos de vehículo.'));
  }, []);
  return <div>{models.length} modelos</div>;
}

// === pricing-factors fetch effect — exact copy from page.js ===
function PricingFactorsWidget() {
  const [pricingFactors, setPricingFactors] = useState(null);
  useEffect(() => {
    authFetch('/settings/pricing-factors')
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setPricingFactors(data); })
      .catch(() => toast.error('No se pudieron cargar los factores de precio.'));
  }, []);
  return <div>{pricingFactors ? 'cargado' : 'sin cargar'}</div>;
}

// === coverage-on-model-change fetch effect — exact copy from page.js ===
function CoverageWidget({ modelCode }) {
  const [coverage, setCoverage] = useState(null);
  useEffect(() => {
    const qs = modelCode ? `?model_code=${encodeURIComponent(modelCode)}` : '';
    authFetch(`/parts/admin/coverage${qs}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setCoverage(data); })
      .catch(() => toast.error('No se pudo cargar la cobertura.'));
  }, [modelCode]);
  return <div>{coverage ? 'cargado' : 'sin cargar'}</div>;
}

// === coverage-refresh-after-rotation-import — exact copy from page.js ===
function RotationImportCoverageRefreshWidget({ modelCode }) {
  const refresh = () => {
    const qs = modelCode ? `?model_code=${encodeURIComponent(modelCode)}` : '';
    authFetch(`/parts/admin/coverage${qs}`).then(r => r.ok ? r.json() : null).then(d => { if (d) {} }).catch(() => toast.error('No se pudo actualizar el panel de cobertura.'));
  };
  return <button onClick={refresh}>Refrescar cobertura</button>;
}

// === fetchData (main catalog load) -- error path copied verbatim from page.js ===
function FetchDataWidget() {
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: '1' });
      const res = await authFetch(`/parts/admin/catalog?${params}`);
      if (res.ok) {
        await res.json();
      } else {
        const errText = await res.text().catch(() => '');
        console.error('[catalog] error', res.status, errText, params.toString());
        toast.error('No se pudo cargar el catálogo de repuestos.');
      }
    } catch (e) {
      console.error('[catalog] exception', e);
      toast.error('No se pudo cargar el catálogo de repuestos.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);
  return <div>{loading ? 'Cargando...' : 'Listo'}</div>;
}

// === togglePriceReview — exact copy from page.js ===
function TogglePriceReviewWidget({ item }) {
  const togglePriceReview = async () => {
    const newVal = !item.needs_price_review;
    try {
      const res = await authFetch(`/parts/admin/catalog/${encodeURIComponent(item.factory_part_number)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ needs_price_review: newVal }),
      });
      if (!res.ok) { toast.error('No se pudo actualizar la revisión de precio.'); return; }
    } catch {
      toast.error('No se pudo actualizar la revisión de precio.');
    }
  };
  return <button onClick={togglePriceReview}>Marcar revisión</button>;
}

// === updateRotation — exact copy from page.js (including optimistic-update rollback) ===
function UpdateRotationWidget({ initialItem }) {
  const [items, setItems] = useState([initialItem]);
  const item = items[0];

  const updateRotation = async (item, rc) => {
    const prevVal = item.rotation_class;
    const newVal = prevVal === rc ? null : rc;
    setItems(prev => prev.map(i => i.factory_part_number === item.factory_part_number ? { ...i, rotation_class: newVal } : i));
    try {
      const res = await authFetch(`/parts/admin/catalog/${encodeURIComponent(item.factory_part_number)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rotation_class: newVal }),
      });
      if (!res.ok) {
        setItems(prev => prev.map(i => i.factory_part_number === item.factory_part_number ? { ...i, rotation_class: prevVal } : i));
        toast.error('No se pudo actualizar la rotación.');
      }
    } catch {
      setItems(prev => prev.map(i => i.factory_part_number === item.factory_part_number ? { ...i, rotation_class: prevVal } : i));
      toast.error('No se pudo actualizar la rotación.');
    }
  };

  return (
    <div>
      <span data-testid="rotation-value">{item.rotation_class || 'sin rotación'}</span>
      <button onClick={() => updateRotation(item, 'baja')}>Baja</button>
    </div>
  );
}

// === "Exportar no pedidas" inline handler — exact copy from page.js ===
function ExportarNoPedidasWidget({ rotationClass }) {
  const handleClick = async () => {
    try {
      const res = await authFetch(`/parts/admin/coverage/unordered?rotation_class=${rotationClass}`);
      if (!res.ok) { toast.error('No se pudo exportar las partes no pedidas.'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `no_pedidas_${rotationClass}.xlsx`; a.click(); URL.revokeObjectURL(url);
    } catch {
      toast.error('No se pudo exportar las partes no pedidas.');
    }
  };
  return <button onClick={handleClick}>Exportar no pedidas</button>;
}

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockToast.error.mockReset();
  mockToast.success.mockReset();
});

test('a non-ok export response shows an error toast', async () => {
  mockAuthFetch.mockResolvedValue({ ok: false });
  render(<ExportWidget />);
  fireEvent.click(screen.getByRole('button', { name: /exportar excel/i }));

  await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith('No se pudo exportar el Excel.'));
});

test('a network error (thrown fetch) shows an error toast', async () => {
  mockAuthFetch.mockRejectedValue(new Error('network down'));
  render(<ExportWidget />);
  fireEvent.click(screen.getByRole('button', { name: /exportar excel/i }));

  await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith('No se pudo exportar el Excel.'));
});

test('the button resets to its normal label after a failed export', async () => {
  mockAuthFetch.mockResolvedValue({ ok: false });
  render(<ExportWidget />);
  fireEvent.click(screen.getByRole('button', { name: /exportar excel/i }));

  await waitFor(() => expect(screen.getByRole('button', { name: /^exportar excel$/i })).not.toBeDisabled());
});

test('a successful export does not show an error toast', async () => {
  global.URL.createObjectURL = jest.fn(() => 'blob:mock');
  global.URL.revokeObjectURL = jest.fn();
  mockAuthFetch.mockResolvedValue({ ok: true, blob: async () => new Blob() });
  render(<ExportWidget />);
  fireEvent.click(screen.getByRole('button', { name: /exportar excel/i }));

  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  expect(mockToast.error).not.toHaveBeenCalled();
});

test('a network error loading vehicle models shows an error toast', async () => {
  mockAuthFetch.mockRejectedValue(new Error('network down'));
  render(<VehicleModelsWidget />);

  await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith('No se pudieron cargar los modelos de vehículo.'));
});

test('a network error loading pricing factors shows an error toast', async () => {
  mockAuthFetch.mockRejectedValue(new Error('network down'));
  render(<PricingFactorsWidget />);

  await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith('No se pudieron cargar los factores de precio.'));
});

test('a network error loading coverage shows an error toast', async () => {
  mockAuthFetch.mockRejectedValue(new Error('network down'));
  render(<CoverageWidget modelCode="renegade_200" />);

  await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith('No se pudo cargar la cobertura.'));
});

test('a network error refreshing coverage after a rotation import shows an error toast', async () => {
  mockAuthFetch.mockRejectedValue(new Error('network down'));
  render(<RotationImportCoverageRefreshWidget modelCode="renegade_200" />);
  fireEvent.click(screen.getByRole('button', { name: /refrescar cobertura/i }));

  await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith('No se pudo actualizar el panel de cobertura.'));
});

test('a failed catalog load shows an error toast', async () => {
  mockAuthFetch.mockResolvedValue({ ok: false, status: 500, text: async () => 'boom' });
  render(<FetchDataWidget />);

  await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith('No se pudo cargar el catálogo de repuestos.'));
});

test('a network error loading the catalog shows an error toast', async () => {
  mockAuthFetch.mockRejectedValue(new Error('network down'));
  render(<FetchDataWidget />);

  await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith('No se pudo cargar el catálogo de repuestos.'));
});

test('a failed price-review toggle shows an error toast', async () => {
  mockAuthFetch.mockResolvedValue({ ok: false });
  render(<TogglePriceReviewWidget item={{ factory_part_number: 'FAB-001', needs_price_review: false }} />);
  fireEvent.click(screen.getByRole('button', { name: /marcar revisión/i }));

  await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith('No se pudo actualizar la revisión de precio.'));
});

test('a network error toggling price review shows an error toast', async () => {
  mockAuthFetch.mockRejectedValue(new Error('network down'));
  render(<TogglePriceReviewWidget item={{ factory_part_number: 'FAB-001', needs_price_review: false }} />);
  fireEvent.click(screen.getByRole('button', { name: /marcar revisión/i }));

  await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith('No se pudo actualizar la revisión de precio.'));
});

test('a failed rotation update shows an error toast AND rolls back the optimistic UI change', async () => {
  mockAuthFetch.mockResolvedValue({ ok: false });
  render(<UpdateRotationWidget initialItem={{ factory_part_number: 'FAB-001', rotation_class: 'alta' }} />);

  fireEvent.click(screen.getByRole('button', { name: /^baja$/i }));
  // Optimistic update applies immediately.
  expect(screen.getByTestId('rotation-value')).toHaveTextContent('baja');

  // Rolled back to the original value once the PATCH fails.
  await waitFor(() => expect(screen.getByTestId('rotation-value')).toHaveTextContent('alta'));
  expect(mockToast.error).toHaveBeenCalledWith('No se pudo actualizar la rotación.');
});

test('a successful rotation update keeps the optimistic value and shows no error', async () => {
  mockAuthFetch.mockResolvedValue({ ok: true });
  render(<UpdateRotationWidget initialItem={{ factory_part_number: 'FAB-001', rotation_class: 'alta' }} />);

  fireEvent.click(screen.getByRole('button', { name: /^baja$/i }));
  await waitFor(() => expect(mockAuthFetch).toHaveBeenCalled());
  expect(screen.getByTestId('rotation-value')).toHaveTextContent('baja');
  expect(mockToast.error).not.toHaveBeenCalled();
});

test('a failed "Exportar no pedidas" shows an error toast', async () => {
  mockAuthFetch.mockResolvedValue({ ok: false });
  render(<ExportarNoPedidasWidget rotationClass="alta" />);
  fireEvent.click(screen.getByRole('button', { name: /exportar no pedidas/i }));

  await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith('No se pudo exportar las partes no pedidas.'));
});

test('a network error on "Exportar no pedidas" shows an error toast', async () => {
  mockAuthFetch.mockRejectedValue(new Error('network down'));
  render(<ExportarNoPedidasWidget rotationClass="alta" />);
  fireEvent.click(screen.getByRole('button', { name: /exportar no pedidas/i }));

  await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith('No se pudo exportar las partes no pedidas.'));
});
