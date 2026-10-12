import "server-only";
import { cache } from "react";
import { getDb, schema } from "../db";
import { interpretarEstado, type EstadoOperador } from "../domain/estado";

export type { EstadoOperador };

export const leerEstado = cache(async (): Promise<EstadoOperador> => {
  const db = await getDb();
  const filas = await db.select().from(schema.estado);
  return interpretarEstado(Object.fromEntries(filas.map((f) => [f.clave, f.valor])));
});

export async function leerClaveEstado(clave: string): Promise<unknown> {
  const db = await getDb();
  const filas = await db.select().from(schema.estado);
  return filas.find((f) => f.clave === clave)?.valor ?? null;
}

export async function guardarEstado(clave: string, valor: unknown): Promise<void> {
  const db = await getDb();
  const ahora = new Date().toISOString();
  await db
    .insert(schema.estado)
    .values({ clave, valor, actualizado: ahora })
    .onConflictDoUpdate({ target: schema.estado.clave, set: { valor, actualizado: ahora } });
}
