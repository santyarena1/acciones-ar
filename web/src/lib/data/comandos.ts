import "server-only";
import { desc, isNull } from "drizzle-orm";
import { getDb, schema } from "../db";

export type TipoComando = "depositar_practica" | "reiniciar_practica" | "revisar";

export async function encolarComando(tipo: TipoComando, datos: Record<string, unknown> = {}): Promise<void> {
  const db = await getDb();
  await db.insert(schema.comandos).values({ tipo, datos, ts: new Date().toISOString() });
}

export interface ComandoPendiente {
  id: number;
  tipo: string;
  ts: string;
  datos: Record<string, unknown>;
}

export async function comandosPendientes(): Promise<ComandoPendiente[]> {
  const db = await getDb();
  return db
    .select({ id: schema.comandos.id, tipo: schema.comandos.tipo, ts: schema.comandos.ts, datos: schema.comandos.datos })
    .from(schema.comandos)
    .where(isNull(schema.comandos.procesado))
    .orderBy(desc(schema.comandos.id))
    .limit(20);
}
