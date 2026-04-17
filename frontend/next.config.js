/** @type {import('next').NextConfig} */
const nextConfig = {
  // Requerido para el Dockerfile de producción (multi-stage standalone build)
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/dashboard',
        destination: '/',
      },
    ]
  },
}

module.exports = nextConfig
