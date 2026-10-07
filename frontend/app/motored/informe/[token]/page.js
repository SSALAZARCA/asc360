/**
 * Public asesor report link (no auth, deliberately NOT wrapped in MotoredLayout: the session guard
 * is per page, so omitting the wrapper is what makes this route public). Server component so it
 * can export metadata; all behavior lives in InformeContainer.
 */
import InformeContainer from '../../../../components/motored/informe/InformeContainer';

export const metadata = {
  title: 'Tu informe · Motored',
  robots: { index: false, follow: false },
};

export default async function InformePage({ params }) {
  const { token } = await params;
  return <InformeContainer token={token} />;
}
