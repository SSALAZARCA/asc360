import './globals.css';

export const metadata = {
  title: 'UM Colombia - Admin Dashboard',
  description: 'Gestión avanzada de la red de servicio post-venta UM Colombia',
};

export default function RootLayout({ children }) {
  return (
    <html lang="es">
      <body>
        {children}
      </body>
    </html>
  );
}
