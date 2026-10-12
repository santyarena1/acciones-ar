import { describe, expect, test } from "vitest";
import { anios, diaAR, fechaCorta, haceCuanto, hora, mesAnio, numero, pct, plata, plataCorta, pp, tituloDia, tono } from "./format";

describe("plata", () => {
  test("agrupa miles con punto y lleva signo $ con espacio", () => {
    expect(plata(1234567)).toBe("$ 1.234.567");
    expect(plata(693625.41)).toBe("$ 693.625");
    expect(plata(0)).toBe("$ 0");
  });
  test("negativos con signo menos tipográfico y positivos con + si se pide", () => {
    expect(plata(-1611.4)).toBe("−$ 1.611");
    expect(plata(200000, { signo: true })).toBe("+$ 200.000");
    expect(plata(-0.2)).toBe("$ 0");
  });
  test("decimales con coma", () => {
    expect(plata(1801.46, { decimales: 2 })).toBe("$ 1.801,46");
  });
  test("valores inválidos -> guion", () => {
    expect(plata(null)).toBe("—");
    expect(plata(Number.NaN)).toBe("—");
    expect(plata("12")).toBe("—");
  });
});

describe("pct y pp", () => {
  test("fracción a porcentaje con coma", () => {
    expect(pct(0.123)).toBe("12,3%");
    expect(pct(0.3, { decimales: 0 })).toBe("30%");
    expect(pct(-0.0023, { signo: true })).toBe("−0,2%");
    expect(pct(0.05, { signo: true })).toBe("+5,0%");
    expect(pct(0)).toBe("0,0%");
  });
  test("puntos porcentuales", () => {
    expect(pp(0.021)).toBe("+2,1 pp");
    expect(pp(-0.005)).toBe("−0,5 pp");
  });
});

describe("otros números", () => {
  test("numero y plataCorta", () => {
    expect(numero(1234.5, 1)).toBe("1.234,5");
    expect(plataCorta(1_234_567)).toBe("$ 1,2 M");
    expect(plataCorta(850_000)).toBe("$ 850 mil");
    expect(plataCorta(-12_500_000)).toBe("−$ 13 M");
  });
  test("tono", () => {
    expect(tono(0.01)).toBe("sube");
    expect(tono(-0.01)).toBe("baja");
    expect(tono(0.0001)).toBe("neutro");
    expect(tono(null)).toBe("neutro");
  });
  test("años y meses", () => {
    expect(anios(1.71)).toBe("1,7 años");
    expect(anios(0.48)).toBe("6 meses");
    expect(anios(0.05)).toBe("1 mes");
  });
});

describe("fechas en hora argentina", () => {
  const ts = "2026-10-11T23:25:22-03:00";
  test("día y hora", () => {
    expect(diaAR(ts)).toBe("2026-10-11");
    expect(diaAR("2026-10-12T02:10:00Z")).toBe("2026-10-11");
    expect(hora(ts)).toBe("23:25");
  });
  test("fecha corta omite el año en curso", () => {
    expect(fechaCorta(ts, new Date("2026-10-12T12:00:00Z"))).toBe("11/10");
    expect(fechaCorta(ts, new Date("2027-01-02T12:00:00Z"))).toBe("11/10/2026");
  });
  test("título de día y hace cuánto", () => {
    const ahora = new Date("2026-10-12T15:00:00-03:00");
    expect(tituloDia("2026-10-12", ahora)).toBe("Hoy");
    expect(tituloDia("2026-10-11", ahora)).toBe("Ayer");
    expect(tituloDia("2026-10-05", ahora)).toMatch(/lunes 5 de octubre/);
    expect(haceCuanto("2026-10-12T14:55:00-03:00", ahora)).toBe("hace 5 min");
    expect(haceCuanto("2026-10-12T12:00:00-03:00", ahora)).toBe("hace 3 h");
    expect(haceCuanto(null, ahora)).toBe("nunca");
  });
  test("mes y año de vencimiento", () => {
    expect(mesAnio("2027-05-31")).toMatch(/may.* 2027/);
    expect(mesAnio(null)).toBe("—");
  });
});
