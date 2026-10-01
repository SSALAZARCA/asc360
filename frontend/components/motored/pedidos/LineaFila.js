'use client';
/** One line of the pedido: "Cantidad a pedir" is an input only when `edicion.editable` and the line is orderable. */
import { formatCOP } from '../../../lib/motored/formatCOP';
import CantidadCelda, { AvisoCantidad } from './CantidadCelda';
import CantidadEditableCell from './CantidadEditableCell';
import { etiquetaExclusion, etiquetaQuiebre, unidades } from './formato';
import { textoRecorte } from './tope';
import { mutedStyle, numStyle, recorteFondoStyle, recorteMarcaStyle, stickyColStyle, tdCompactStyle as tdStyle } from './styles';

function Cantidad({ linea, edicion, onHistorial }) {
  const editable = Boolean(edicion && edicion.editable && !linea.motivo_exclusion);
  if (!editable) {
    const aviso = edicion && <AvisoCantidad mensaje={edicion.errores[linea.id]} />;
    return <CantidadCelda linea={linea} onHistorial={onHistorial} aviso={aviso} />;
  }
  return (
    <CantidadEditableCell
      linea={linea} guardando={edicion.guardando[linea.id]} error={edicion.errores[linea.id]}
      onGuardar={edicion.guardar} onOlvidarError={edicion.olvidarError} onHistorial={onHistorial}
    />
  );
}

/** `recorte` is the cut a recorte proposal would make on this line: the row is highlighted and says to how many. */
export default function LineaFila({ linea, edicion, onHistorial, recorte }) {
  const excluida = Boolean(linea.motivo_exclusion);
  const fondo = recorte ? recorteFondoStyle : {};
  return (
    <tr style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)', opacity: excluida ? 0.65 : 1, ...fondo }}>
      <td style={{ ...tdStyle, ...stickyColStyle, ...fondo, fontWeight: 600 }}>{linea.codigo_referencia}</td>
      <td style={{ ...tdStyle, whiteSpace: 'normal', minWidth: '130px' }}>
        {linea.nombre_parte}
        {excluida && <span style={{ ...mutedStyle, display: 'block' }}>{`Excluida: ${etiquetaExclusion(linea.motivo_exclusion)}`}</span>}
      </td>
      <td style={tdStyle}>{linea.clase || '—'}</td>
      <td style={{ ...tdStyle, ...numStyle }}>{linea.unidad_empaque}</td>
      <td style={{ ...tdStyle, ...numStyle }}>{formatCOP(linea.precio)}</td>
      <td style={{ ...tdStyle, ...numStyle }}>{unidades(linea.pedido_sugerido)}</td>
      <td style={{ ...tdStyle, ...numStyle }}>
        <Cantidad linea={linea} edicion={edicion} onHistorial={onHistorial} />
        {recorte && <span style={recorteMarcaStyle}>{textoRecorte(recorte)}</span>}
      </td>
      <td style={{ ...tdStyle, ...numStyle }}>{formatCOP(linea.valor_pedido)}</td>
      <td style={tdStyle}>{etiquetaQuiebre(linea.estado_quiebre)}</td>
    </tr>
  );
}
