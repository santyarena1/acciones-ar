/** Token de sesión firmado (HS256). Sin dependencias de Node: lo usa también el middleware (edge). */
import { SignJWT, jwtVerify } from "jose";

export const COOKIE_SESION = "sesion";
export const DURACION_SESION_SEG = 30 * 24 * 60 * 60;
const EMISOR = "acciones-ar";

export function claveSesion(secreto: string | undefined): Uint8Array {
  if (!secreto || secreto.length < 32) throw new Error("SESSION_SECRET falta o tiene menos de 32 caracteres.");
  return new TextEncoder().encode(secreto);
}

export async function firmarSesion(email: string, secreto: string | undefined, ahoraSeg = Math.floor(Date.now() / 1000)): Promise<string> {
  return new SignJWT({})
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(email)
    .setIssuer(EMISOR)
    .setIssuedAt(ahoraSeg)
    .setExpirationTime(ahoraSeg + DURACION_SESION_SEG)
    .sign(claveSesion(secreto));
}

/** Devuelve el email si el token es válido y no venció; si no, null. */
export async function verificarSesion(token: string | undefined, secreto: string | undefined): Promise<string | null> {
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, claveSesion(secreto), { issuer: EMISOR, algorithms: ["HS256"] });
    return typeof payload.sub === "string" ? payload.sub : null;
  } catch {
    return null;
  }
}
