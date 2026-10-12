import { readFileSync } from "node:fs";
import { join } from "node:path";

/** Ruta del contrato SQL compartido con el motor (`<repo>/db/schema.sql`). */
export function rutaEsquema(): string {
  return process.env.SCHEMA_SQL_PATH ?? join(process.cwd(), "..", "db", "schema.sql");
}

export function leerEsquema(): string {
  return readFileSync(rutaEsquema(), "utf8");
}

/** Tablas y columnas declaradas en el SQL (parser mínimo para CREATE TABLE ... ( col tipo, ... )). */
export function columnasDelEsquema(sql: string): Record<string, string[]> {
  const sinComentarios = sql.replace(/--[^\n]*/g, "");
  const out: Record<string, string[]> = {};
  const re = /CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\(([\s\S]*?)\);/gi;
  for (const m of sinComentarios.matchAll(re)) {
    const [, tabla, cuerpo] = m;
    if (!tabla || !cuerpo) continue;
    out[tabla] = cuerpo
      .split("\n")
      .map((l) => l.trim().split(/\s+/)[0] ?? "")
      .filter((c) => c && !/^(PRIMARY|UNIQUE|CONSTRAINT|FOREIGN|CHECK)$/i.test(c));
  }
  return out;
}
