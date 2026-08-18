import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backendUrl}/api/:path*` },
      { source: "/media/:path*", destination: `${backendUrl}/media/:path*` },
    ];
  },
};

export default nextConfig;
