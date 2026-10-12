import "server-only";
import { cache } from "react";
import { desc, eq } from "drizzle-orm";
import { getDb, schema } from "../db";
import { prepararCorrida, type Corrida } from "../domain/corrida";

/** Última corrida del modo pedido; si ese modo todavía no corrió, la última de cualquier modo. */
export const ultimaCorrida = cache(async (modo: string): Promise<Corrida | null> => {
  const db = await getDb();
  const [delModo] = await db
    .select()
    .from(schema.corridas)
    .where(eq(schema.corridas.modo, modo))
    .orderBy(desc(schema.corridas.creada))
    .limit(1);
  const fila =
    delModo ?? (await db.select().from(schema.corridas).orderBy(desc(schema.corridas.creada)).limit(1))[0];
  return fila ? prepararCorrida(fila) : null;
});
