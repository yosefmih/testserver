import type { NextConfig } from "next";

// Read the Python backend URL from an environment variable
// Fallback to http://localhost:8088 if not set, for local development
const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL || 'http://localhost:8088';

const nextConfig: NextConfig = {
  /* config options here */

  async rewrites() {
    return [
      {
        source: '/api/backend/:path*', // All requests to /api/backend/... will be proxied
        destination: `${PYTHON_BACKEND_URL}/:path*`, // Proxy to the root of the Python server
      },
      // You can add more rewrite rules here if needed for other backends
      // or more specific path mappings.
    ];
  },
};

export default nextConfig;
