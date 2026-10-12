/**
 * Carga datos REALES locales del motor en la base de desarrollo (PGlite en web/.pglite) para ver la app.
 * Lee en tiempo de ejecución (no se commitea nada): ../reports/corridas/*, ../data/operador/bitacora.jsonl,
 * ../data/operador/estado.json, ../data/paper_state.json y ../data/usuario.yaml.
 *
 *   pnpm seed                     # carga (pisa corridas/estado/paper/preferencias; agrega eventos si la tabla está vacía)
 *   pnpm seed --reset             # vacía todo menos usuarios y vuelve a cargar
 *   pnpm seed --historia-demo     # además inventa 45 días de "fotos" para ver la curva (marcadas demo:true)
 *
 * Cerrá `pnpm dev` antes de correrlo: PGlite no admite dos procesos sobre la misma carpeta.
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { parse as parseCsv } from "csv-parse/sync";
import { parse as parseYaml } from "yaml";
import { sql } from "drizzle-orm";
import { abrirPglite } from "../src/lib/db/pglite";
import * as schema from "../src/lib/db/schema";

const RAIZ = resolve(process.cwd(), "..");
const args = new Set(process.argv.slice(2));

function valor(v: string): unknown {
  if (v === "") return null;
  if (v === "True") return true;
  if (v === "False") return false;
  if (/^-?\d+(\.\d+)?(e[-+]?\d+)?$/i.test(v)) return Number(v);
  return v;
}

/** CSV de pandas -> filas (orient='records'); la primera columna sin nombre es el índice. */
function csv(ruta: string, indice?: string): Record<string, unknown>[] {
  if (!existsSync(ruta)) return [];
  const filas = parseCsv(readFileSync(ruta, "utf8"), { columns: (h: string[]) => h.map((c, i) => (i === 0 && c === "" && indice ? indice : c)), skip_empty_lines: true }) as Record<string, string>[];
  return filas.map((f) => Object.fromEntries(Object.entries(f).map(([k, v]) => [k, valor(v)])));
}

function stampAIso(stamp: string): string {
  const m = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})$/.exec(stamp);
  if (!m) return new Date().toISOString();
  return new Date(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:00-03:00`).toISOString();
}

function json<T>(ruta: string): T | null {
  return existsSync(ruta) ? (JSON.parse(readFileSync(ruta, "utf8")) as T) : null;
}

async function main() {
  const db = await abrirPglite();
  if (args.has("--reset")) {
    await db.execute(sql`TRUNCATE corridas, eventos, estado, paper, preferencias, comandos, reportes, secretos RESTART IDENTITY`);
    console.log("Base vaciada (menos usuarios).");
  }

  // corridas
  const dirCorridas = join(RAIZ, "reports", "corridas");
  const stamps = existsSync(dirCorridas) ? readdirSync(dirCorridas).filter((s) => existsSync(join(dirCorridas, s, "meta.json"))).sort() : [];
  for (const stamp of stamps) {
    const d = join(dirCorridas, stamp);
    const meta = json<Record<string, unknown>>(join(d, "meta.json")) ?? {};
    const modo = String(meta.broker ?? "").toLowerCase() === "iol" ? "live" : "paper";
    const fila = {
      stamp,
      creada: stampAIso(stamp),
      modo,
      meta,
      ranking: csv(join(d, "ranking.csv"), "ticker"),
      rentaFija: csv(join(d, "renta_fija.csv"), "ticker_iol"),
      objetivos: csv(join(d, "objetivos.csv"), "ticker"),
      ordenes: csv(join(d, "ordenes.csv")),
      guia: existsSync(join(d, "guia.md")) ? readFileSync(join(d, "guia.md"), "utf8") : "",
    };
    await db.insert(schema.corridas).values(fila).onConflictDoUpdate({ target: schema.corridas.stamp, set: fila });
  }
  console.log(`Corridas: ${stamps.length}`);

  // eventos (bitácora)
  const rutaBit = join(RAIZ, "data", "operador", "bitacora.jsonl");
  const [{ n }] = (await db.execute(sql`SELECT count(*)::int AS n FROM eventos`)).rows as [{ n: number }];
  if (existsSync(rutaBit) && n === 0) {
    const lineas = readFileSync(rutaBit, "utf8").split("\n").filter(Boolean);
    let k = 0;
    for (const l of lineas) {
      try {
        const { ts, tipo, modo, ...datos } = JSON.parse(l) as Record<string, unknown>;
        await db.insert(schema.eventos).values({ ts: String(ts), tipo: String(tipo), modo: typeof modo === "string" ? modo : null, datos });
        k++;
      } catch {
        /* línea rota: se saltea */
      }
    }
    console.log(`Eventos: ${k}`);
  } else {
    console.log(n ? `Eventos: ya había ${n}, no se duplican (usá --reset)` : "Eventos: sin bitácora local");
  }

  // estado
  const est = json<Record<string, unknown>>(join(RAIZ, "data", "operador", "estado.json"));
  if (est) {
    const { pausado, motivo_pausa, ...resto } = est;
    const filas: Record<string, unknown> = { ...resto, pausado: { pausado: Boolean(pausado), motivo: motivo_pausa ?? null } };
    for (const [clave, v] of Object.entries(filas)) {
      if (v === undefined || v === null) continue; // el motor guarda null como ausencia
      await db.insert(schema.estado).values({ clave, valor: v }).onConflictDoUpdate({ target: schema.estado.clave, set: { valor: v } });
    }
    console.log(`Estado: ${Object.keys(filas).join(", ")}`);
  }

  // cartera de práctica
  const paper = json<unknown>(join(RAIZ, "data", "paper_state.json"));
  if (paper) {
    await db.insert(schema.paper).values({ clave: "cartera", valor: paper }).onConflictDoUpdate({ target: schema.paper.clave, set: { valor: paper } });
    console.log("Cartera de práctica: ok");
  }

  // preferencias
  const rutaUsr = join(RAIZ, "data", "usuario.yaml");
  if (existsSync(rutaUsr)) {
    const prefs = (parseYaml(readFileSync(rutaUsr, "utf8")) ?? {}) as Record<string, unknown>;
    await db.insert(schema.preferencias).values({ clave: "usuario", valor: prefs }).onConflictDoUpdate({ target: schema.preferencias.clave, set: { valor: prefs } });
    console.log("Preferencias: ok");
  }

  if (args.has("--historia-demo")) await historiaDemo(db);
  console.log("Listo.");
  process.exit(0);
}

/** 45 días de fotos inventadas (paseo aleatorio con semilla fija) para ver la curva. Solo desarrollo. */
async function historiaDemo(db: Awaited<ReturnType<typeof abrirPglite>>) {
  let semilla = 7;
  const azar = () => ((semilla = (semilla * 16807) % 2147483647) / 2147483647) - 0.5;
  let indice = 1;
  let bm = 1;
  // termina justo antes de la primera foto real, para empalmar sin saltos
  const [primera] = (await db.execute(sql`SELECT ts, datos FROM eventos WHERE tipo = 'foto' ORDER BY ts LIMIT 1`)).rows as { ts: string; datos: { indice?: number; bm_indice?: number; valor?: number } }[];
  const fin = primera ? new Date(primera.ts).getTime() : Date.now();
  const puntos: { ts: string; i: number; b: number }[] = [];
  for (let d = 45; d >= 1; d--) {
    const dia = new Date(fin - d * 86_400_000);
    if (dia.getUTCDay() === 0 || dia.getUTCDay() === 6) continue;
    indice *= 1 + azar() * 0.022 + 0.0009;
    bm *= 1 + azar() * 0.018 + 0.0004;
    dia.setUTCHours(19, 30, 0, 0);
    puntos.push({ ts: dia.toISOString(), i: indice, b: bm });
  }
  // normalizado: el arranque vale 1 y empalma con la primera foto real (índices relativos)
  const fi = (primera?.datos.indice ?? 1) / indice;
  const fb = (primera?.datos.bm_indice ?? 1) / bm;
  const valorFin = primera?.datos.valor ?? 500_000;
  for (const p of puntos) {
    await db.insert(schema.eventos).values({
      ts: p.ts,
      tipo: "foto",
      modo: "paper",
      datos: { valor: Math.round(valorFin * (p.i / indice)), indice: Number((p.i * fi).toFixed(6)), bm_indice: Number((p.b * fb).toFixed(6)), demo: true },
    });
  }
  console.log("Historia demo: ok (fotos marcadas demo:true)");
}

main().catch((e: unknown) => {
  console.error(e);
  process.exit(1);
});
