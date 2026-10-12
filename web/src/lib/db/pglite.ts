import { PGlite } from "@electric-sql/pglite";
import { drizzle } from "drizzle-orm/pglite";
import type { PgliteDatabase } from "drizzle-orm/pglite";
import * as schema from "./schema";
import { leerEsquema } from "./esquema-sql";

/** Abre (o crea) la base local y aplica `db/schema.sql` (idempotente). `PGLITE_DIR=memory://` para tests. */
export async function abrirPglite(dir = process.env.PGLITE_DIR ?? ".pglite"): Promise<PgliteDatabase<typeof schema>> {
  const client = new PGlite(dir);
  await client.exec(leerEsquema());
  return drizzle(client, { schema });
}
