import "server-only";
import { neon } from "@neondatabase/serverless";
import { drizzle as drizzleNeon } from "drizzle-orm/neon-http";
import type { NeonHttpDatabase } from "drizzle-orm/neon-http";
import * as schema from "./schema";

/**
 * Base de datos:
 * - Producción (Vercel): Neon por HTTP (`DATABASE_URL`). Sin conexiones persistentes: ideal para funciones.
 * - Desarrollo y tests: PGlite (Postgres en WASM) en `web/.pglite`, con el mismo `db/schema.sql`.
 *
 * Ambos drivers exponen la misma API de Drizzle para lo que usa la app (select/insert/update con returning,
 * sin transacciones interactivas), así que se tipa como el de Neon.
 */
export type Db = NeonHttpDatabase<typeof schema>;

const g = globalThis as unknown as { __db?: Promise<Db> };

/**
 * URL de Neon a usar. Fuera de producción se ignora DATABASE_URL salvo que se pida explícitamente
 * (USAR_DATABASE_URL_EN_DEV=1): así el desarrollo y los tests nunca tocan una base real por accidente.
 */
export function urlBase(env: NodeJS.ProcessEnv = process.env): string | null {
  const url = env.DATABASE_URL?.trim();
  if (!url) return null;
  if (env.NODE_ENV !== "production" && env.USAR_DATABASE_URL_EN_DEV !== "1") return null;
  return url;
}

export function usaPglite(): boolean {
  return urlBase() === null;
}

async function crear(): Promise<Db> {
  const url = urlBase();
  if (url) return drizzleNeon(neon(url), { schema });
  if (process.env.VERCEL) throw new Error("Falta DATABASE_URL en el entorno de Vercel.");
  const { abrirPglite } = await import("./pglite");
  return (await abrirPglite()) as unknown as Db;
}

export function getDb(): Promise<Db> {
  g.__db ??= crear().catch((e: unknown) => {
    g.__db = undefined;
    throw e;
  });
  return g.__db;
}

export { schema };
