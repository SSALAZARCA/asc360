/**
 * Public satisfaction survey (no auth, not wrapped in MotoredLayout). Manrope is
 * loaded here only, so no other Motored route pays for it. Server component so
 * it can export metadata; all behavior lives in EncuestaContainer.
 */
import { Manrope } from 'next/font/google';
import EncuestaContainer from '../../../components/motored/encuesta/EncuestaContainer';

const manrope = Manrope({ subsets: ['latin'], weight: ['500', '700'], variable: '--enc-font' });

export const metadata = {
  title: 'Encuesta de satisfacción · Motored',
  robots: { index: false, follow: false },
};

export default function EncuestaPage() {
  return <EncuestaContainer fontClassName={manrope.variable} />;
}
