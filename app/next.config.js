/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return {
      beforeFiles: [
        // trade.somacosf.com root serves the mission-control terminal UI
        {
          source: '/',
          destination: '/trade/index.html',
          has: [{ type: 'host', value: 'trade.somacosf.com' }],
        },
        {
          source: '/about',
          destination: '/trade/about.html',
          has: [{ type: 'host', value: 'trade.somacosf.com' }],
        },
      ],
      afterFiles: [
        { source: '/thesis', destination: '/thesis/index.html' },
      ],
      fallback: [],
    };
  },
};
module.exports = nextConfig;
