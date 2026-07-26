/** @type {import('next').NextConfig} */
const backendOrigin = (process.env.PAPERPLANE_BACKEND_ORIGIN ?? "http://127.0.0.1:8000")
  .replace(/\/+$/, "");

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendOrigin}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
