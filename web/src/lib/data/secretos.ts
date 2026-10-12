import "server-only";
import { eq, inArray } from "drizzle-orm";
import { getDb, schema } from "../db";
import { cifrar, claveDelEntorno, descifrar } from "../crypto";

export type ClaveSecreto = "IOL_USERNAME" | "IOL_PASSWORD" | "TELEGRAM_TOKEN" | "TELEGRAM_CHAT_ID";
const TODAS: ClaveSecreto[] = ["IOL_USERNAME", "IOL_PASSWORD", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"];

export async function guardarSecretos(valores: Partial<Record<ClaveSecreto, string>>): Promise<void> {
  const clave = claveDelEntorno();
  const db = await getDb();
  const ahora = new Date().toISOString();
  for (const [k, v] of Object.entries(valores)) {
    if (v === undefined) continue;
    const valor = cifrar(v, clave);
    await db
      .insert(schema.secretos)
      .values({ clave: k, valor, actualizado: ahora })
      .onConflictDoUpdate({ target: schema.secretos.clave, set: { valor, actualizado: ahora } });
  }
}

export async function leerSecreto(k: ClaveSecreto): Promise<string | null> {
  const db = await getDb();
  const [f] = await db.select().from(schema.secretos).where(eq(schema.secretos.clave, k));
  if (!f) return null;
  return descifrar(f.valor, claveDelEntorno());
}

/** Qué secretos están cargados (sin descifrarlos) y cuándo se actualizaron. */
export async function secretosCargados(): Promise<Partial<Record<ClaveSecreto, string>>> {
  const db = await getDb();
  const filas = await db
    .select({ clave: schema.secretos.clave, actualizado: schema.secretos.actualizado })
    .from(schema.secretos)
    .where(inArray(schema.secretos.clave, TODAS));
  return Object.fromEntries(filas.map((f) => [f.clave, f.actualizado]));
}

export async function borrarSecretos(claves: ClaveSecreto[]): Promise<void> {
  const db = await getDb();
  await db.delete(schema.secretos).where(inArray(schema.secretos.clave, claves));
}
