import { readFileSync } from "node:fs";
import { join } from "node:path";
import { parse } from "yaml";
import { describe, expect, test } from "vitest";
import { PERFILES } from "./perfiles";

/** Los perfiles de la web tienen que ser idénticos a los del motor (config/settings.yaml). */
describe("perfiles sincronizados con config/settings.yaml", () => {
  const settings = parse(readFileSync(join(process.cwd(), "..", "config", "settings.yaml"), "utf8")) as {
    perfiles: Record<string, Record<string, number>>;
  };

  test("mismos perfiles", () => {
    expect(PERFILES.map((p) => p.id).sort()).toEqual(Object.keys(settings.perfiles).sort());
  });

  test("mismo reparto por clase", () => {
    for (const p of PERFILES) expect(p.reparto).toEqual(settings.perfiles[p.id]);
  });

  test("cada reparto suma 100%", () => {
    for (const p of PERFILES) expect(Object.values(p.reparto).reduce((a, b) => a + b, 0)).toBeCloseTo(1, 6);
  });
});
