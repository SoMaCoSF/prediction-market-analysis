/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: '/thesis', destination: '/thesis/index.html' },
    ];
  },
};
module.exports = nextConfig;
