import { describe, expect, test } from "vitest";
import { montoSchema } from "./acciones";

describe("montoSchema (montos escritos a mano)", () => {
  test.each([
    ["500.000", 500000],
    ["500000", 500000],
    ["$ 1.234.567,50", 1234567.5],
    [" 100.000 ", 100000],
  ])("%s -> %d", (entrada, esperado) => {
    expect(montoSchema.parse(entrada)).toBe(esperado);
  });

  test.each(["", "abc", "0", "-100", "1e20"])("rechaza %s", (entrada) => {
    expect(montoSchema.safeParse(entrada).success).toBe(false);
  });
});
