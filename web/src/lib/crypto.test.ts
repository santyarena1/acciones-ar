import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
import { ErrorCifrado, cifrar, claveDesdeBase64, descifrar } from "./crypto";

/** Vector escrito por el motor en Python (src/secretos.py): la web tiene que leerlo byte a byte igual. */
const vector = JSON.parse(readFileSync(join(process.cwd(), "..", "db", "vector_cifrado.json"), "utf8")) as {
  clave_base64: string;
  nonce_hex: string;
  texto: string;
  valor: string;
};

describe("compatibilidad con el motor (Python AESGCM)", () => {
  const clave = claveDesdeBase64(vector.clave_base64);

  test("descifra el vector de db/vector_cifrado.json", () => {
    expect(descifrar(vector.valor, clave)).toBe(vector.texto);
  });

  test("con el mismo nonce produce exactamente el mismo valor", () => {
    expect(cifrar(vector.texto, clave, Buffer.from(vector.nonce_hex, "hex"))).toBe(vector.valor);
  });
});

describe("cifrado", () => {
  const clave = claveDesdeBase64(Buffer.alloc(32, 7).toString("base64"));

  test("ida y vuelta con nonce aleatorio (dos cifrados distintos del mismo texto)", () => {
    const a = cifrar("contraseña-ñ", clave);
    const b = cifrar("contraseña-ñ", clave);
    expect(a).not.toBe(b);
    expect(a.startsWith("v1:")).toBe(true);
    expect(descifrar(a, clave)).toBe("contraseña-ñ");
  });

  test("detecta datos alterados", () => {
    const v = cifrar("hola", clave);
    const raw = Buffer.from(v.slice(3), "base64");
    raw[raw.length - 1]! ^= 1;
    expect(() => descifrar(`v1:${raw.toString("base64")}`, clave)).toThrow(ErrorCifrado);
  });

  test("rechaza clave equivocada, formato desconocido y datos truncados", () => {
    const v = cifrar("hola", clave);
    const otra = claveDesdeBase64(Buffer.alloc(32, 8).toString("base64"));
    expect(() => descifrar(v, otra)).toThrow(ErrorCifrado);
    expect(() => descifrar("v2:abc", clave)).toThrow(/Formato/);
    expect(() => descifrar("v1:AAAA", clave)).toThrow(/truncado/);
  });

  test("valida la clave de entorno", () => {
    expect(() => claveDesdeBase64(undefined)).toThrow(/Falta/);
    expect(() => claveDesdeBase64(Buffer.alloc(16).toString("base64"))).toThrow(/32 bytes/);
  });
});
