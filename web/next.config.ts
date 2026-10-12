import type { NextConfig } from "next";

/**
 * Headers de seguridad estáticos acá; la CSP va en el middleware porque usa un nonce por pedido.
 */
const seguridad = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "X-DNS-Prefetch-Control", value: "off" },
];

const config: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  // PGlite (solo desarrollo) trae WASM: que Node lo cargue tal cual en vez de empaquetarlo.
  serverExternalPackages: ["@electric-sql/pglite"],
  experimental: { serverActions: { bodySizeLimit: "64kb" } },
  async headers() {
    return [{ source: "/:path*", headers: seguridad }];
  },
};

export default config;
