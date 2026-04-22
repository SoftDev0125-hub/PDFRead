/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/files/:path*',
        destination: 'http://127.0.0.1:8012/api/files/:path*',
      },
      {
        source: '/api/results/:path*',
        destination: 'http://127.0.0.1:8012/api/results/:path*',
      },
      {
        source: '/api/health',
        destination: 'http://127.0.0.1:8012/api/health',
      },
    ]
  },
}

export default nextConfig

