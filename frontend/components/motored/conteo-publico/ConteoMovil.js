/**
 * Phone layout (prototype "ConteoCelular"): location chip, camera, last
 * reading with big −/+, and bottom buttons "Escribir código", "Lo contado
 * (N)" and "Reconteos asignados (N)". A Bluetooth scanner works as a
 * keyboard and is caught with no field focused.
 */
import { Suspense, lazy, useRef, useState } from 'react';
import { AvisoLectura, BannerPendientes, NotaRonda, Rechazos } from './Avisos';
import BarraUbicacion from './BarraUbicacion';
import ListaContado from './ListaContado';
import { ListaReconteos, TareaActiva } from './Reconteos';
import UltimaLectura from './UltimaLectura';
import { C, MONO, botonNeutro, campo, pantalla } from './estilos';
import { useCapturaTeclado } from './teclado';
import { TEXTOS } from './textos';
import PruebaBadge from './PruebaBadge';

const CamaraEscaner = lazy(() => import('./CamaraEscaner'));

function camaraDisponible() {
  return 'BarcodeDetector' in window
    && Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
}

function EntradaManual({ entradaRef, onCodigo }) {
  const [valor, setValor] = useState('');
  const enviar = (e) => {
    e.preventDefault();
    if (!valor.trim()) return;
    onCodigo(valor, 'MANUAL');
    setValor('');
  };
  return (
    <form onSubmit={enviar} style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
      <label style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13, fontWeight: 700 }}>
        Escriba el código
        <input
          ref={entradaRef}
          type="text"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          value={valor}
          onChange={(e) => setValor(e.target.value)}
          style={{ ...campo, fontFamily: MONO }}
        />
      </label>
      <button type="submit" style={{ ...botonNeutro, minHeight: 46, padding: '10px 16px', background: C.tinta, color: C.blanco, border: 'none' }}>
        Sumar
      </button>
    </form>
  );
}

function Hoja({ titulo, onCerrar, children }) {
  return (
    <div role="dialog" aria-label={titulo} style={{ position: 'fixed', inset: 0, zIndex: 20, background: C.fondo, overflow: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <button type="button" onClick={onCerrar} style={{ ...botonNeutro, alignSelf: 'flex-start', minHeight: 44 }}>Cerrar</button>
      {children}
    </div>
  );
}

export default function ConteoMovil({ conteo, onSalir }) {
  const [camara] = useState(camaraDisponible);
  const [manual, setManual] = useState(false);
  const [hoja, setHoja] = useState(null);
  const entrada = useRef(null);
  const { info, ubicacion, tareas, tarea, lecturas: l } = conteo;
  const asignadas = tareas.filter((t) => t.estado === 'ASIGNADO').length;
  useCapturaTeclado((codigo) => l.registrarCodigo(codigo, 'ESCANER'), !hoja);

  const escribir = () => {
    setManual(true);
    setTimeout(() => entrada.current && entrada.current.focus(), 0);
  };
  const elegir = (id) => {
    conteo.elegirTarea(id);
    setHoja(null);
  };

  return (
    <div style={{ ...pantalla, maxWidth: 600, margin: '0 auto', width: '100%' }}>
      <header style={{ padding: '14px 16px', background: C.tinta, color: C.blanco, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 800, fontSize: 16 }}>{info.sucursal}</span>
            {info.esPrueba && <PruebaBadge />}
          </span>
          <span style={{ fontSize: 12, color: C.borde }}>{info.etiqueta}</span>
        </div>
        <button type="button" onClick={onSalir} style={{ background: 'transparent', border: 'none', color: C.blanco, fontFamily: 'inherit', fontSize: 13, fontWeight: 700, textDecoration: 'underline', minHeight: 44 }}>
          Salir
        </button>
      </header>
      <BannerPendientes sinConexion={conteo.sinConexion} pendientes={conteo.pendientes} />
      <main style={{ flex: 1, padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <BarraUbicacion compacta ubicacion={ubicacion} ubicaciones={conteo.ubicaciones} ocupado={conteo.ocupado} onCambiar={conteo.cambiarUbicacion} />
        <TareaActiva tarea={tarea} onTerminar={conteo.terminarTarea} onSoltar={() => conteo.elegirTarea(null)} />
        <NotaRonda estado={info.estado} tarea={tarea} />
        {camara ? (
          <Suspense fallback={<div style={{ height: 230, borderRadius: 14, background: '#27272a' }} />}>
            <CamaraEscaner onCodigo={l.registrarCodigo} />
          </Suspense>
        ) : (
          <div style={{ fontSize: 13, color: C.medio }}>{TEXTOS.sinCamara}</div>
        )}
        {(manual || !camara) && <EntradaManual entradaRef={entrada} onCodigo={l.registrarCodigo} />}
        <AvisoLectura aviso={l.aviso} onForzar={l.forzarDesconocido} />
        <Rechazos rechazos={l.rechazos} />
        <UltimaLectura compacta ultima={l.ultima} total={l.total} onAjustar={l.ajustar} />
      </main>
      <nav style={{ position: 'sticky', bottom: 0, padding: '12px 16px 20px', background: C.blanco, borderTop: `1px solid ${C.borde}`, display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
        <button type="button" onClick={escribir} style={botonNeutro}>Escribir código</button>
        <button type="button" onClick={() => setHoja('contado')} style={botonNeutro}>{`Lo contado (${l.filas.length})`}</button>
        <button type="button" onClick={() => setHoja('reconteos')} style={{ ...botonNeutro, gridColumn: 'span 2', border: 'none', background: C.alertaFondo, color: C.alerta }}>
          {`Reconteos asignados (${asignadas})`}
        </button>
      </nav>
      {hoja === 'contado' && (
        <Hoja titulo="Lo contado" onCerrar={() => setHoja(null)}>
          <ListaContado ubicacion={ubicacion} filas={l.filas} ultimaCodigo={l.ultima && l.ultima.codigo} onSeleccionar={(f) => { l.seleccionar(f); setHoja(null); }} />
        </Hoja>
      )}
      {hoja === 'reconteos' && (
        <Hoja titulo="Reconteos asignados" onCerrar={() => setHoja(null)}>
          <ListaReconteos tareas={tareas} tareaActivaId={tarea && tarea.id} onElegir={elegir} />
        </Hoja>
      )}
    </div>
  );
}
