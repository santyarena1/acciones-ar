import { getTableConfig } from "drizzle-orm/pg-core";
import { describe, expect, test } from "vitest";
import { columnasDelEsquema, leerEsquema } from "./esquema-sql";
import { tablas } from "./schema";

/** El esquema Drizzle de la web tiene que reflejar exactamente db/schema.sql (contrato con el motor). */
describe("schema.ts == db/schema.sql", () => {
  const sql = columnasDelEsquema(leerEsquema());

  test("mismas tablas", () => {
    expect(Object.keys(tablas).sort()).toEqual(Object.keys(sql).sort());
  });

  for (const [nombre, tabla] of Object.entries(tablas)) {
    test(`columnas de ${nombre}`, () => {
      const cfg = getTableConfig(tabla);
      expect(cfg.name).toBe(nombre);
      expect(cfg.columns.map((c) => c.name).sort()).toEqual([...(sql[nombre] ?? [])].sort());
    });
  }
});
