import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";

/**
 * Cifrado de secretos compatible byte a byte con el motor en Python
 * (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`, sin datos asociados):
 *   valor = "v1:" + base64(nonce[12] || ciphertext || tag[16])
 * Clave: CLAVE_CIFRADO = 32 bytes en base64.
 */
const PREFIJO = "v1:";
const NONCE = 12;
const TAG = 16;

export class ErrorCifrado extends Error {}

export function claveDesdeBase64(b64: string | undefined): Buffer {
  if (!b64) throw new ErrorCifrado("Falta CLAVE_CIFRADO en el entorno.");
  const clave = Buffer.from(b64.trim(), "base64");
  if (clave.length !== 32) throw new ErrorCifrado("CLAVE_CIFRADO tiene que ser de 32 bytes en base64.");
  return clave;
}

export function cifrar(texto: string, clave: Buffer, nonce: Buffer = randomBytes(NONCE)): string {
  if (nonce.length !== NONCE) throw new ErrorCifrado("Nonce inválido.");
  const c = createCipheriv("aes-256-gcm", clave, nonce);
  const ct = Buffer.concat([c.update(texto, "utf8"), c.final()]);
  return PREFIJO + Buffer.concat([nonce, ct, c.getAuthTag()]).toString("base64");
}

export function descifrar(valor: string, clave: Buffer): string {
  if (!valor.startsWith(PREFIJO)) throw new ErrorCifrado("Formato de secreto desconocido.");
  const raw = Buffer.from(valor.slice(PREFIJO.length), "base64");
  if (raw.length < NONCE + TAG) throw new ErrorCifrado("Secreto truncado.");
  const nonce = raw.subarray(0, NONCE);
  const tag = raw.subarray(raw.length - TAG);
  const ct = raw.subarray(NONCE, raw.length - TAG);
  const d = createDecipheriv("aes-256-gcm", clave, nonce);
  d.setAuthTag(tag);
  try {
    return Buffer.concat([d.update(ct), d.final()]).toString("utf8");
  } catch {
    throw new ErrorCifrado("No se pudo descifrar (clave incorrecta o dato alterado).");
  }
}

export function claveDelEntorno(): Buffer {
  return claveDesdeBase64(process.env.CLAVE_CIFRADO);
}
