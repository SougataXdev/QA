import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // react-pdf uses canvas — needs this webpack config
  webpack: (config) => {
    // Fix for pdfjs-dist using node APIs
    config.resolve.alias.canvas = false;
    return config;
  },
  // Turbopack equivalent
  turbopack: {
    resolveAlias: {
      canvas: '',
    },
  },
};

export default nextConfig;
