/** @type {import('next').NextConfig} */

// Force HTTPS for the API URL before Next.js inlines it into the bundle
if (process.env.NEXT_PUBLIC_API_URL) {
  process.env.NEXT_PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL.replace(
    /^http:\/\/(?!localhost)/,
    'https://'
  );
}

const nextConfig = {
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
