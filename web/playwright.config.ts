import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * E2E contra la app compilada (next start) con una base PGlite propia (.pglite-e2e) cargada con `pnpm seed`.
 * Usa SOLO web/.env.local (nunca busca .env en carpetas de arriba) y fuerza DATABASE_URL vacío.
 */
function envLocal(): Record<string, string> {
  const ruta = join(process.cwd(), ".env.local");
  if (!existsSync(ruta)) return {};
  const out: Record<string, string> = {};
  for (const l of readFileSync(ruta, "utf8").split(/\r?\n/)) {
    const m = /^([A-Z0-9_]+)=(.*)$/.exec(l);
    if (m?.[1]) out[m[1]] = m[2] ?? "";
  }
  return out;
}

const env = { ...envLocal(), DATABASE_URL: "", PGLITE_DIR: ".pglite-e2e" };
for (const [k, v] of Object.entries(env)) process.env[k] ??= v;
const PUERTO = Number(process.env.E2E_PORT ?? 3219);
const BASE = process.env.E2E_BASE_URL ?? `http://localhost:${PUERTO}`;

/** Si el Chromium de esta versión de Playwright no está bajado, usa uno ya instalado (PW_CHROMIUM). */
const chromiumLocal = process.env.PW_CHROMIUM ?? join(homedir(), "AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe");

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: BASE,
    locale: "es-AR",
    timezoneId: "America/Argentina/Buenos_Aires",
    launchOptions: existsSync(chromiumLocal) ? { executablePath: chromiumLocal } : {},
  },
  projects: [
    { name: "telefono", use: { ...devices["Pixel 7"], viewport: { width: 375, height: 812 }, browserName: "chromium" } },
    { name: "escritorio", use: { viewport: { width: 1440, height: 900 }, browserName: "chromium" } },
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: `pnpm seed --reset --historia-demo && pnpm start --port ${PUERTO}`,
        url: `${BASE}/login`,
        timeout: 180_000,
        reuseExistingServer: false,
        env: { ...env, PGLITE_DIR: ".pglite-e2e" },
      },
});
