import './globals.css';

export const metadata = {
  title: 'ASC360 - UM Colombia',
  description: 'Red de servicio post-venta UM Colombia',
  manifest: '/manifest.json',
  icons: {
    icon: '/logo.png',
    apple: '/logo.png',
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="es">
      <head>
        <link rel="manifest" href="/manifest.json" />
        <link rel="apple-touch-icon" href="/logo.png" />
        <meta name="theme-color" content="#ff5f33" />
      </head>
      <body>
        {children}
      </body>
    </html>
  );
}
