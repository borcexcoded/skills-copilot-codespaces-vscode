import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* In production, /api/* is proxied to the backend (Railway).
     Set NEXT_PUBLIC_API_URL to the backend URL. */
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
