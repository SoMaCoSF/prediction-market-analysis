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
        // mc.somacosf.com — same mission-control terminal
        {
          source: '/',
          destination: '/trade/index.html',
          has: [{ type: 'host', value: 'mc.somacosf.com' }],
        },
        {
          source: '/about',
          destination: '/trade/about.html',
          has: [{ type: 'host', value: 'mc.somacosf.com' }],
        },
        // dry.somacosf.com — public paper-engine terminal
        {
          source: '/',
          destination: '/dry/index.html',
          has: [{ type: 'host', value: 'dry.somacosf.com' }],
        },
        // tim.somacosf.com — guest phone betting surface
        {
          source: '/',
          destination: '/tim/index.html',
          has: [{ type: 'host', value: 'tim.somacosf.com' }],
        },
        // time.somacosf.com — the AI times magazine
        {
          source: '/',
          destination: '/time/index.html',
          has: [{ type: 'host', value: 'time.somacosf.com' }],
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
