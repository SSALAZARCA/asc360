export const metadata = {
  title: 'ASC360',
  description: 'Red de Servicio UM Colombia',
};

export default function TgLayout({ children }) {
  return (
    <div style={{ minHeight: '100vh', background: '#0a0a0c', color: '#fff', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      {children}
    </div>
  );
}
