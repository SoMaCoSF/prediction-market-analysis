/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return {
      beforeFiles: [
        // trade.somacosf.com — mission-control terminal
        { source: '/', destination: '/trade/index.html', has: [{ type: 'host', value: 'trade.somacosf.com' }] },
        { source: '/about', destination: '/trade/about.html', has: [{ type: 'host', value: 'trade.somacosf.com' }] },
        { source: '/status', destination: '/trade/status.html', has: [{ type: 'host', value: 'trade.somacosf.com' }] },
        // mc.somacosf.com — same terminal
        { source: '/', destination: '/trade/index.html', has: [{ type: 'host', value: 'mc.somacosf.com' }] },
        { source: '/about', destination: '/trade/about.html', has: [{ type: 'host', value: 'mc.somacosf.com' }] },
        // dry.somacosf.com — public paper-engine terminal
        { source: '/', destination: '/dry/index.html', has: [{ type: 'host', value: 'dry.somacosf.com' }] },
        // tim.somacosf.com — guest phone betting surface
        { source: '/', destination: '/tim/index.html', has: [{ type: 'host', value: 'tim.somacosf.com' }] },
        // time.somacosf.com — the AI times magazine
        { source: '/', destination: '/time/index.html', has: [{ type: 'host', value: 'time.somacosf.com' }] },
        { source: '/about', destination: '/time/about.html', has: [{ type: 'host', value: 'time.somacosf.com' }] },
        { source: '/funds', destination: '/time/funds.html', has: [{ type: 'host', value: 'time.somacosf.com' }] },
        { source: '/oracle', destination: '/time/oracle.html', has: [{ type: 'host', value: 'time.somacosf.com' }] },
        // poly.somacosf.com — polymarket control panel
        { source: '/', destination: '/poly/index.html', has: [{ type: 'host', value: 'poly.somacosf.com' }] },
      ],
      afterFiles: [
        { source: '/thesis', destination: '/thesis/index.html' },
      ],
      fallback: [],
    };
  },
};
module.exports = nextConfig;
