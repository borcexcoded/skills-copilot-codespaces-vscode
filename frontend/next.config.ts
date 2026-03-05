import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* In production on Vercel, /api/* is handled by Python serverless functions.
     In local dev, proxy to the FastAPI backend. */
  async rewrites() {
    return process.env.NODE_ENV === "development"
      ? [{ source: "/api/:path*", destination: "http://localhost:8000/api/:path*" }]
      : [];
  },
};

export default nextConfig;
