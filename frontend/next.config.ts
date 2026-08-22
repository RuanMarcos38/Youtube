import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  experimental: {
    // O Editor aceita arquivos de até 500 MB. No Next.js 16 o proxy interno
    // possui um limite de body independente; sem este ajuste uploads grandes
    // podem ser truncados antes de chegar ao FastAPI e terminar em HTTP 500.
    proxyClientMaxBodySize: "520mb",
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backendUrl}/api/:path*` },
      { source: "/media/:path*", destination: `${backendUrl}/media/:path*` },
    ];
  },
};

export default nextConfig;
