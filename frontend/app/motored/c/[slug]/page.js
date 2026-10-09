/**
 * Public counting page for pairs (odd/motored-conteos-inventario WU13/WU14):
 * `<MOTORED_PUBLIC_URL>/motored/c/<slug>`. No login and deliberately NOT
 * wrapped in MotoredLayout: the session guard is applied per page, so
 * omitting the wrapper is what makes this route public (same as
 * `motored/encuesta` and `motored/informe/[token]`). Server component so it
 * can export noindex metadata; all behavior lives in ConteoPublicoContainer.
 */
import ConteoPublicoContainer from '../../../../components/motored/conteo-publico/ConteoPublicoContainer';

export const metadata = {
  title: 'Conteo de inventario · Motored',
  robots: { index: false, follow: false },
};

export default async function ConteoPublicoPage({ params }) {
  const { slug } = await params;
  return <ConteoPublicoContainer slug={slug} />;
}
