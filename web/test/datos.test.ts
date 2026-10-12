/**
 * Integración: capa de datos contra PGlite en memoria con el mismo db/schema.sql que usa el motor.
 */
import { beforeAll, describe, expect, test } from "vitest";
import { corridaCruda } from "./fixtures";

process.env.PGLITE_DIR = "memory://";
delete process.env.DATABASE_URL;
process.env.CLAVE_CIFRADO = Buffer.alloc(32, 3).toString("base64");

const { getDb, schema, urlBase } = await import("@/lib/db");
const { ultimaCorrida } = await import("@/lib/data/corridas");
const { leerEstado, guardarEstado, leerClaveEstado } = await import("@/lib/data/estado");
const { eventosRecientes, fotos, registrarEvento, ultimaRevision, loginsFallidos } = await import("@/lib/data/eventos");
const { guardarPreferencias, leerPreferencias } = await import("@/lib/data/preferencias");
const { guardarSecretos, leerSecreto, secretosCargados, borrarSecretos } = await import("@/lib/data/secretos");
const { encolarComando, comandosPendientes } = await import("@/lib/data/comandos");

beforeAll(async () => {
  const db = await getDb();
  await db.insert(schema.corridas).values({ ...corridaCruda, creada: "2026-10-12T02:25:00Z" });
  await db.insert(schema.corridas).values({ ...corridaCruda, stamp: "20261010_1130", creada: "2026-10-10T14:30:00Z" });
  await db.insert(schema.eventos).values([
    { ts: "2026-10-11T22:58:45-03:00", tipo: "orden", modo: null, datos: { ticker: "YPFD", lado: "COMPRAR", cantidad: 6, precio: 8105 } },
    { ts: "2026-10-11T23:00:00-03:00", tipo: "aporte", modo: "paper", datos: { monto: 495236, inicial: true } },
    { ts: "2026-10-11T23:01:00-03:00", tipo: "aporte", modo: "live", datos: { monto: 1 } },
    { ts: "2026-10-11T23:25:22-03:00", tipo: "foto", modo: "paper", datos: { valor: 693625, indice: 1, bm_indice: 1 } },
    { ts: "2026-10-12T14:30:00-03:00", tipo: "foto", modo: "paper", datos: { valor: 700000, indice: 1.01, bm_indice: null } },
    { ts: "2026-10-12T14:31:00-03:00", tipo: "corrida", modo: "paper", datos: { ordenes: 0 } },
  ]);
});

describe("capa de datos (PGlite)", () => {
  test("fuera de producción nunca usa DATABASE_URL salvo pedido explícito", () => {
    expect(urlBase({ NODE_ENV: "development", DATABASE_URL: "postgres://x" } as NodeJS.ProcessEnv)).toBeNull();
    expect(urlBase({ NODE_ENV: "development", DATABASE_URL: "postgres://x", USAR_DATABASE_URL_EN_DEV: "1" } as NodeJS.ProcessEnv)).toBe("postgres://x");
    expect(urlBase({ NODE_ENV: "production", DATABASE_URL: "postgres://x" } as NodeJS.ProcessEnv)).toBe("postgres://x");
  });

  test("última corrida del modo, con fallback a cualquier modo", async () => {
    expect((await ultimaCorrida("paper"))?.stamp).toBe("20261011_2325");
    expect((await ultimaCorrida("live"))?.stamp).toBe("20261011_2325");
  });

  test("eventos del modo + los que no tienen modo", async () => {
    const evs = await eventosRecientes({ tipos: ["orden", "aporte"], modo: "paper" });
    expect(evs.map((e) => e.tipo)).toEqual(["aporte", "orden"]);
  });

  test("fotos en orden cronológico y bm faltante como null", async () => {
    const f = await fotos("paper");
    expect(f.map((x) => x.indice)).toEqual([1, 1.01]);
    expect(f[1]?.bmIndice).toBeNull();
  });

  test("última revisión", async () => {
    expect(new Date((await ultimaRevision())!).toISOString()).toBe("2026-10-12T17:31:00.000Z");
  });

  test("estado: escribir y leer pausa y aportes", async () => {
    await guardarEstado("pausado", { pausado: true, motivo: "manual" });
    await guardarEstado("aportes", { paper: { total: 695236, caja: 1, caja_ts: "x" } });
    const e = await leerEstado();
    expect(e.pausado).toBe(true);
    expect(e.aportes.paper?.total).toBe(695236);
    expect(await leerClaveEstado("aportes")).toEqual({ paper: { total: 695236, caja: 1, caja_ts: "x" } });
  });

  test("preferencias: mezcla sin perder lo que puso el motor", async () => {
    await guardarPreferencias({ operador: { perfil: "agresivo", horizonte: "mediano" } });
    await guardarPreferencias({ operador: { modo: "live" } });
    expect(await leerPreferencias()).toEqual({ operador: { perfil: "agresivo", horizonte: "mediano", modo: "live" } });
  });

  test("secretos cifrados en la base (nunca en claro)", async () => {
    await guardarSecretos({ IOL_USERNAME: "usuario", IOL_PASSWORD: "clave secreta" });
    const db = await getDb();
    const filas = await db.select().from(schema.secretos);
    expect(filas.every((f) => f.valor.startsWith("v1:") && !f.valor.includes("clave"))).toBe(true);
    expect(await leerSecreto("IOL_PASSWORD")).toBe("clave secreta");
    expect(Object.keys(await secretosCargados()).sort()).toEqual(["IOL_PASSWORD", "IOL_USERNAME"]);
    await borrarSecretos(["IOL_USERNAME", "IOL_PASSWORD"]);
    expect(await leerSecreto("IOL_USERNAME")).toBeNull();
  });

  test("comandos y logins fallidos", async () => {
    await encolarComando("depositar_practica", { monto: 100000 });
    expect((await comandosPendientes())[0]).toMatchObject({ tipo: "depositar_practica", datos: { monto: 100000 } });
    await registrarEvento("login_fallido", { ip: "abc" });
    expect((await loginsFallidos(new Date(Date.now() - 60_000).toISOString())).length).toBe(1);
  });
});
