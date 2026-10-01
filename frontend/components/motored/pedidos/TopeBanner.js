'use client';
/**
 * Budget cap banner of ONE tienda pedido. A draft above its cap shows the
 * figures, the lines a recorte would cut and "Aplicar recorte" (nothing is
 * cut until the user confirms); a closed or sent pedido above its cap only
 * informs. Under the cap, without a cap, with the mode off, or without data,
 * it renders nothing.
 */
import InfoTooltip from '../InfoTooltip';
import { ACTION_ICONS } from '../actionIcons';
import { formatCOP } from '../../../lib/motored/formatCOP';
import RecortePreview from './RecortePreview';
import { plural } from './formato';
import { mutedStyle, numStyle, topeBannerStyle } from './styles';
import { hayExceso, resumenRecorte, tieneRecortes } from './tope';

export const TOPE_TEXTO = 'Tope de presupuesto: lo máximo, en pesos, que el administrador fijó para el pedido de esta tienda. Es un aviso: nada se recorta sin que usted lo confirme.';

function Cifra({ titulo, valor, ayuda, fuerte }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', ...numStyle }}>
      <span style={{ ...mutedStyle, display: 'inline-flex', alignItems: 'center' }}>{titulo}{ayuda && <InfoTooltip text={ayuda} />}</span>
      <span style={{ fontSize: '1.05rem', fontWeight: fuerte ? 800 : 700 }}>{formatCOP(valor)}</span>
    </div>
  );
}

function Cifras({ tope, valor, exceso }) {
  return (
    <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
      <Cifra titulo="Tope" valor={tope} ayuda={TOPE_TEXTO} />
      <Cifra titulo="Valor a pedir" valor={valor} />
      <Cifra titulo="Exceso" valor={exceso} fuerte />
    </div>
  );
}

function Notas({ propuesta }) {
  const n = propuesta.lineas_sin_precio;
  const residual = Number(propuesta.exceso_residual) > 0;
  return (
    <>
      {n > 0 && <span style={mutedStyle}>{`${n} ${plural(n, 'línea sin precio no suma', 'líneas sin precio no suman')} al valor.`}</span>}
      {residual && tieneRecortes(propuesta) && (
        <span style={{ ...mutedStyle, fontWeight: 600 }}>
          {`Aun con el recorte quedaría un exceso de ${formatCOP(propuesta.exceso_residual)}: las referencias de clase A y D no se recortan.`}
        </span>
      )}
    </>
  );
}

function Recorte({ propuesta, puedeAplicar, onAplicar }) {
  const { lineas, liberado } = resumenRecorte(propuesta);
  const Icono = ACTION_ICONS['Aplicar recorte'];
  if (!tieneRecortes(propuesta)) {
    return <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>No hay líneas que se puedan recortar: el exceso está en referencias de clase A y D, que no se recortan.</span>;
  }
  return (
    <>
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>
          {`${plural(lineas, 'Se recortaría', 'Se recortarían')} ${lineas} ${plural(lineas, 'línea', 'líneas')} y se liberarían ${formatCOP(liberado)}.`}
        </span>
        {puedeAplicar && (
          <button
            type="button" className="motored-btn motored-btn-primary" onClick={onAplicar}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', minHeight: '44px' }}
          >
            {Icono && <Icono size={16} aria-hidden="true" />}
            Aplicar recorte
          </button>
        )}
      </div>
      <RecortePreview recortes={propuesta.recortes} />
    </>
  );
}

function BannerBorrador({ propuesta, puedeAplicar, onAplicar }) {
  return (
    <section aria-label="Tope de presupuesto" style={topeBannerStyle}>
      <h2 style={{ margin: 0, fontSize: '0.95rem' }}>Pedido por encima del tope de presupuesto</h2>
      <Cifras tope={propuesta.tope} valor={propuesta.valor_actual} exceso={propuesta.exceso} />
      <Notas propuesta={propuesta} />
      <Recorte propuesta={propuesta} puedeAplicar={puedeAplicar} onAplicar={onAplicar} />
    </section>
  );
}

function BannerCerrado({ cerrado }) {
  return (
    <section aria-label="Tope de presupuesto" style={topeBannerStyle}>
      <h2 style={{ margin: 0, fontSize: '0.95rem' }}>Este pedido quedó por encima del tope de presupuesto</h2>
      <Cifras tope={cerrado.tope} valor={cerrado.valor_a_pedir} exceso={cerrado.exceso} />
      <span style={mutedStyle}>El pedido ya no se puede recortar. Para ajustarlo, reábralo.</span>
    </section>
  );
}

/** `propuesta` is the recorte proposal of a draft, `cerrado` the cap row of a closed or sent pedido. */
export default function TopeBanner({ propuesta, cerrado, puedeAplicar, onAplicar }) {
  if (hayExceso(propuesta)) return <BannerBorrador propuesta={propuesta} puedeAplicar={puedeAplicar} onAplicar={onAplicar} />;
  if (cerrado && Number(cerrado.exceso) > 0) return <BannerCerrado cerrado={cerrado} />;
  return null;
}
