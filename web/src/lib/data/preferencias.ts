import "server-only";
import { cache } from "react";
import { eq } from "drizzle-orm";
import { getDb, schema } from "../db";
import { mezclar, type Preferencias } from "../domain/preferencias";

export { modoDe, perfilDe, type Preferencias } from "../domain/preferencias";

const CLAVE = "usuario";

export const leerPreferencias = cache(async (): Promise<Preferencias> => {
  const db = await getDb();
  const [fila] = await db.select().from(schema.preferencias).where(eq(schema.preferencias.clave, CLAVE));
  const v = fila?.valor;
  return v && typeof v === "object" ? (v as Preferencias) : {};
});

export async function guardarPreferencias(cambios: Record<string, unknown>): Promise<void> {
  const db = await getDb();
  const [fila] = await db.select().from(schema.preferencias).where(eq(schema.preferencias.clave, CLAVE));
  const base = fila?.valor && typeof fila.valor === "object" ? fila.valor : {};
  const valor = mezclar(base, cambios);
  const ahora = new Date().toISOString();
  await db
    .insert(schema.preferencias)
    .values({ clave: CLAVE, valor, actualizado: ahora })
    .onConflictDoUpdate({ target: schema.preferencias.clave, set: { valor, actualizado: ahora } });
}
