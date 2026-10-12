import { createHash, timingSafeEqual } from "node:crypto";

/** Comparación de textos en tiempo constante (hashea primero para no filtrar el largo). */
export function igualesSeguro(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return false;
  const ha = createHash("sha256").update(a).digest();
  const hb = createHash("sha256").update(b).digest();
  return timingSafeEqual(ha, hb);
}

/** Huella de la IP para guardar intentos sin guardar la IP en claro. */
export function huellaIp(ip: string, sal: string): string {
  return createHash("sha256").update(`${sal}:${ip}`).digest("hex").slice(0, 16);
}
