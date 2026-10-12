import { modoSchema, type Modo } from "./schemas";
import { PERFIL_POR_DEFECTO, perfilPorId, type PerfilId } from "../perfiles";

export type Preferencias = Record<string, unknown> & { operador?: Record<string, unknown> };

function esObjeto(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

/** Mezcla profunda sin mutar: los objetos se combinan, el resto se pisa. */
export function mezclar(base: Record<string, unknown>, cambios: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...base };
  for (const [k, v] of Object.entries(cambios)) {
    const previo = out[k];
    out[k] = esObjeto(previo) && esObjeto(v) ? mezclar(previo, v) : v;
  }
  return out;
}

export function modoDe(p: Preferencias): Modo {
  const m = modoSchema.safeParse(p.operador?.modo);
  return m.success ? m.data : "paper";
}

export function perfilDe(p: Preferencias): PerfilId {
  const id = p.operador?.perfil;
  return typeof id === "string" && perfilPorId(id) ? (id as PerfilId) : PERFIL_POR_DEFECTO;
}
