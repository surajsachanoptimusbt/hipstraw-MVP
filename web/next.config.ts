import type { NextConfig } from "next";

// The desk API (FastAPI, `hipstraw-mm desk serve`) runs beside this app; the browser only talks to this origin.
const API = process.env.HIPSTRAW_API ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

export default config;
