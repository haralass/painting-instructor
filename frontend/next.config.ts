import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
  // Allow images from the backend
  images: {
    remotePatterns: [
      { protocol: "http",  hostname: "localhost",  port: "8000" },
      { protocol: "http",  hostname: "127.0.0.1",  port: "8000" },
    ],
  },
};

export default nextConfig;
