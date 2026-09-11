import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker-friendly build: bundles only the files needed to run `node
  // server.js`, so the runtime image doesn't need node_modules/npm at all.
  output: "standalone",
};

export default nextConfig;
