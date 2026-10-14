import { describe, expect, test } from "vitest";
import { problemaOperador } from "./problemas";

describe("problemaOperador", () => {
  test("modo real sin IOL conectado: frenado, con enlace a conectar", () => {
    const p = problemaOperador({ modo: "live", iolConectado: false, ultimo: null });
    expect(p?.titulo).toMatch(/frenado/);
    expect(p?.enlace?.href).toBe("/configuracion#iol");
  });

  test("práctica sin IOL no es problema", () => {
    expect(problemaOperador({ modo: "paper", iolConectado: false, ultimo: null })).toBeNull();
  });

  test("último evento es una corrida: sin problema", () => {
    expect(problemaOperador({ modo: "live", iolConectado: true, ultimo: { tipo: "corrida", ts: "x" } })).toBeNull();
  });

  test("errores técnicos se explican sin jerga", () => {
    const login = problemaOperador({ modo: "live", iolConectado: true, ultimo: { tipo: "error", ts: "x", error: "IOLError: Login IOL falló (HTTP 401)." } });
    expect(login?.texto).toMatch(/rechazó el ingreso/);
    const otro = problemaOperador({ modo: "live", iolConectado: true, ultimo: { tipo: "error", ts: "x", error: "KeyError: 'close'" } });
    expect(otro?.texto).not.toMatch(/KeyError/);
  });
});
