import { describe, expect, test } from "vitest";
import { igualesSeguro, huellaIp } from "./igualdad";
import { MAX_GLOBAL, MAX_POR_IP, VENTANA_MS, evaluarIntentos } from "./limite";
import { claveNuevaSchema, coincide, emailSchema, hashear } from "./password";
import { DURACION_SESION_SEG, firmarSesion, verificarSesion } from "./token";

const SECRETO = "x".repeat(40);

describe("token de sesión", () => {
  test("firma y verifica", async () => {
    const t = await firmarSesion("dueno@ejemplo.com", SECRETO);
    expect(await verificarSesion(t, SECRETO)).toBe("dueno@ejemplo.com");
  });
  test("rechaza otro secreto, token alterado o vacío", async () => {
    const t = await firmarSesion("dueno@ejemplo.com", SECRETO);
    expect(await verificarSesion(t, "y".repeat(40))).toBeNull();
    expect(await verificarSesion(`${t.slice(0, -2)}aa`, SECRETO)).toBeNull();
    expect(await verificarSesion(undefined, SECRETO)).toBeNull();
  });
  test("vence a los 30 días", async () => {
    const hace31 = Math.floor(Date.now() / 1000) - DURACION_SESION_SEG - 60;
    const t = await firmarSesion("dueno@ejemplo.com", SECRETO, hace31);
    expect(await verificarSesion(t, SECRETO)).toBeNull();
  });
  test("exige un secreto largo", async () => {
    await expect(firmarSesion("a@b.co", "corto")).rejects.toThrow(/SESSION_SECRET/);
  });
});

describe("contraseñas", () => {
  test("bcrypt: coincide solo con la correcta", async () => {
    const h = await hashear("una frase bien larga");
    expect(h.startsWith("$2")).toBe(true);
    expect(await coincide("una frase bien larga", h)).toBe(true);
    expect(await coincide("otra cosa", h)).toBe(false);
  });
  test("mínimo 10 caracteres", () => {
    expect(claveNuevaSchema.safeParse("123456789").success).toBe(false);
    expect(claveNuevaSchema.safeParse("1234567890").success).toBe(true);
  });
  test("email normalizado", () => {
    expect(emailSchema.parse("  Dueno@Ejemplo.COM ")).toBe("dueno@ejemplo.com");
    expect(emailSchema.safeParse("no-es-email").success).toBe(false);
  });
});

describe("límite de intentos", () => {
  const ahora = 1_000_000_000;
  const intentos = (n: number, ip: string, hace = 1000) => Array.from({ length: n }, () => ({ ip, ts: ahora - hace }));

  test("permite hasta el máximo por IP", () => {
    expect(evaluarIntentos(intentos(MAX_POR_IP - 1, "a"), "a", ahora).permitido).toBe(true);
    const v = evaluarIntentos(intentos(MAX_POR_IP, "a"), "a", ahora);
    expect(v.permitido).toBe(false);
    expect(v.reintentarEnMin).toBe(15);
  });
  test("otra IP no queda bloqueada por la primera", () => {
    expect(evaluarIntentos(intentos(MAX_POR_IP, "a"), "b", ahora).permitido).toBe(true);
  });
  test("bloqueo global ante muchos intentos distribuidos", () => {
    const muchos = Array.from({ length: MAX_GLOBAL }, (_, i) => ({ ip: `ip${i}`, ts: ahora - 1000 }));
    expect(evaluarIntentos(muchos, "nueva", ahora).permitido).toBe(false);
  });
  test("los intentos viejos no cuentan", () => {
    expect(evaluarIntentos(intentos(MAX_POR_IP, "a", VENTANA_MS + 1), "a", ahora).permitido).toBe(true);
  });
});

describe("comparación segura", () => {
  test("igualesSeguro", () => {
    expect(igualesSeguro("abc", "abc")).toBe(true);
    expect(igualesSeguro("abc", "abd")).toBe(false);
    expect(igualesSeguro("abc", "abcd")).toBe(false);
    expect(igualesSeguro(null, "abc")).toBe(false);
  });
  test("huella de IP estable y sin la IP en claro", () => {
    expect(huellaIp("1.2.3.4", "s")).toBe(huellaIp("1.2.3.4", "s"));
    expect(huellaIp("1.2.3.4", "s")).not.toContain("1.2.3.4");
    expect(huellaIp("1.2.3.4", "s")).not.toBe(huellaIp("1.2.3.4", "t"));
  });
});
