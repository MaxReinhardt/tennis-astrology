import type { NextConfig } from "next";

// Under `vercel dev` / production, Services routes /api to the Python service. Running
// `next dev` alone, point API_ORIGIN at a local uvicorn to get the same behaviour.
const apiOrigin = process.env.API_ORIGIN;

const config: NextConfig = {
  async rewrites() {
    return apiOrigin ? [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }] : [];
  },
};

export default config;
