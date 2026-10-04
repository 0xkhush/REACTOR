/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  async rewrites() {
    return [
      { source: '/engine', destination: '/' },
      { source: '/kitchen', destination: '/' },
      { source: '/benchmarks', destination: '/' },
      { source: '/metrics', destination: '/' },
      { source: '/architecture', destination: '/' },
    ]
  },
}

export default nextConfig
