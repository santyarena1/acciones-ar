import "server-only";
import { and, asc, desc, eq, gte, inArray, isNull, or } from "drizzle-orm";
import { getDb, schema } from "../db";
import type { Evento } from "../domain/eventos";

/** Eventos del modo actual o sin modo (el motor registra las órdenes sin columna modo). */
function delModo(modo: string) {
  return or(eq(schema.eventos.modo, modo), isNull(schema.eventos.modo));
}

export async function eventosRecientes(opts: {
  tipos: readonly string[];
  modo: string;
  limite?: number;
  desde?: string;
}): Promise<Evento[]> {
  const db = await getDb();
  const filtros = [inArray(schema.eventos.tipo, [...opts.tipos]), delModo(opts.modo)];
  if (opts.desde) filtros.push(gte(schema.eventos.ts, opts.desde));
  return db
    .select()
    .from(schema.eventos)
    .where(and(...filtros))
    .orderBy(desc(schema.eventos.ts), desc(schema.eventos.id))
    .limit(opts.limite ?? 50);
}

export interface Foto {
  ts: string;
  valor: number;
  indice: number;
  bmIndice: number | null;
}

/** Fotos del valor de la cartera (las escribe el motor en cada revisión), en orden cronológico. */
export async function fotos(modo: string, limite = 2000): Promise<Foto[]> {
  const db = await getDb();
  const filas = await db
    .select({ ts: schema.eventos.ts, datos: schema.eventos.datos })
    .from(schema.eventos)
    .where(and(eq(schema.eventos.tipo, "foto"), delModo(modo)))
    .orderBy(asc(schema.eventos.ts))
    .limit(limite);
  const out: Foto[] = [];
  for (const f of filas) {
    const d = f.datos ?? {};
    const valor = Number(d.valor);
    const indice = Number(d.indice);
    const bm = d.bm_indice === undefined || d.bm_indice === null ? null : Number(d.bm_indice);
    if (Number.isFinite(valor) && Number.isFinite(indice)) {
      out.push({ ts: f.ts, valor, indice, bmIndice: bm !== null && Number.isFinite(bm) ? bm : null });
    }
  }
  return out;
}

export async function registrarEvento(
  tipo: string,
  datos: Record<string, unknown>,
  modo: string | null = null,
): Promise<void> {
  const db = await getDb();
  await db.insert(schema.eventos).values({ tipo, datos, modo, ts: new Date().toISOString() });
}

/** Intentos de ingreso fallidos recientes (para el límite de intentos). */
export async function loginsFallidos(desde: string): Promise<{ ts: string; datos: Record<string, unknown> }[]> {
  const db = await getDb();
  return db
    .select({ ts: schema.eventos.ts, datos: schema.eventos.datos })
    .from(schema.eventos)
    .where(and(eq(schema.eventos.tipo, "login_fallido"), gte(schema.eventos.ts, desde)))
    .limit(500);
}

/** Última revisión del operador (evento 'corrida' o, si no hay, la corrida más nueva). */
export async function ultimaRevision(): Promise<string | null> {
  const db = await getDb();
  const [ev] = await db
    .select({ ts: schema.eventos.ts })
    .from(schema.eventos)
    .where(eq(schema.eventos.tipo, "corrida"))
    .orderBy(desc(schema.eventos.ts))
    .limit(1);
  const [c] = await db
    .select({ creada: schema.corridas.creada })
    .from(schema.corridas)
    .orderBy(desc(schema.corridas.creada))
    .limit(1);
  const a = ev?.ts ?? null;
  const b = c?.creada ?? null;
  if (!a) return b;
  if (!b) return a;
  return new Date(a) > new Date(b) ? a : b;
}
