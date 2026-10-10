/**
 * Desktop / tablet layout (prototype "ConteoPortatil"): header with the
 * pair, tabs "Contar" / "Reconteos asignados (N)", location bar first, the
 * scanner field, the last reading, and the list of what was counted here.
 */
import { useState } from 'react';
import { AvisoLectura, BannerListaSinCargar, BannerPendientes, NotaRonda, Rechazos } from './Avisos';
import BarraUbicacion from './BarraUbicacion';
import EntradaEscaner from './EntradaEscaner';
import ListaContado from './ListaContado';
import { ListaReconteos, TareaActiva } from './Reconteos';
import UltimaLectura from './UltimaLectura';
import { C, pantalla } from './estilos';
import { TEXTOS } from './textos';
import PruebaBadge from './PruebaBadge';

function estiloPestana(activa) {
  return {
    fontFamily: 'inherit', fontSize: 15, fontWeight: activa ? 800 : 700, padding: '10px 18px',
    borderRadius: 999, border: activa ? 'none' : `1px solid ${C.bordeCampo}`,
    background: activa ? C.tinta : C.blanco, color: activa ? C.blanco : C.tinta, cursor: 'pointer',
  };
}

function Pestana({ activa, onClick, children }) {
  return (
    <button type="button" role="tab" aria-selected={activa} onClick={onClick} style={estiloPestana(activa)}>
      {children}
    </button>
  );
}

function Encabezado({ info, onSalir }) {
  return (
    <header style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '14px 32px', background: C.tinta, color: C.blanco }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 800, fontSize: 18 }}>Motored</span>
        <span style={{ fontSize: 15, color: C.borde }}>{`Conteo total · ${info.sucursal || ''}`}</span>
        {info.esPrueba && <PruebaBadge />}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <span style={{ fontSize: 14, color: C.borde }}>{info.etiqueta}</span>
        <button type="button" onClick={onSalir} style={{ background: 'transparent', border: 'none', color: C.blanco, fontFamily: 'inherit', fontSize: 13, fontWeight: 700, textDecoration: 'underline', cursor: 'pointer' }}>
          Salir
        </button>
      </div>
    </header>
  );
}

export default function ConteoEscritorio({ conteo, onSalir }) {
  const [pestana, setPestana] = useState('contar');
  const { info, ubicacion, tareas, tarea, lecturas: l } = conteo;
  const asignadas = tareas.filter((t) => t.estado === 'ASIGNADO').length;
  const elegir = (id) => {
    conteo.elegirTarea(id);
    setPestana('contar');
  };
  return (
    <div style={pantalla}>
      <Encabezado info={info} onSalir={onSalir} />
      <BannerPendientes sinConexion={conteo.sinConexion} pendientes={conteo.pendientes} />
      <BannerListaSinCargar visible={conteo.listaSinCargar} />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, padding: 'clamp(16px, 3vw, 24px) clamp(16px, 3vw, 32px) 40px', alignItems: 'flex-start' }}>
        <div style={{ flex: '999 1 520px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div role="tablist" aria-label="Modo" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Pestana activa={pestana === 'contar'} onClick={() => setPestana('contar')}>Contar</Pestana>
            <Pestana activa={pestana === 'reconteos'} onClick={() => setPestana('reconteos')}>
              {`Reconteos asignados (${asignadas})`}
            </Pestana>
          </div>
          {pestana === 'contar' ? (
            <div role="tabpanel" aria-label="Contar" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <TareaActiva tarea={tarea} onTerminar={conteo.terminarTarea} onSoltar={() => conteo.elegirTarea(null)} />
              <NotaRonda estado={info.estado} tarea={tarea} />
              <BarraUbicacion
                ubicacion={ubicacion}
                ubicaciones={conteo.ubicaciones}
                ocupado={conteo.ocupado}
                onCambiar={conteo.cambiarUbicacion}
              />
              <EntradaEscaner onCodigo={l.registrarCodigo} />
              <div style={{ fontSize: 13, color: C.medio }}>{TEXTOS.ayudaEscaner}</div>
              <UltimaLectura ultima={l.ultima} total={l.total} onAjustar={l.ajustar} />
              <AvisoLectura aviso={l.aviso} onForzar={l.forzarDesconocido} />
              <Rechazos rechazos={l.rechazos} />
            </div>
          ) : (
            <div role="tabpanel" aria-label="Reconteos asignados">
              <ListaReconteos tareas={tareas} tareaActivaId={tarea && tarea.id} onElegir={elegir} />
            </div>
          )}
        </div>
        <ListaContado
          ubicacion={ubicacion}
          filas={l.filas}
          ultimaCodigo={l.ultima && !l.ultima.reconteoId ? l.ultima.codigo : null}
          onSeleccionar={l.seleccionar}
          style={{ flex: '1 1 340px', minWidth: 0 }}
        />
      </div>
    </div>
  );
}
