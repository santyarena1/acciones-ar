/**
 * Perfiles de riesgo. Duplicado de `config/settings.yaml` (perfiles); `perfiles.test.ts` verifica que sigan
 * iguales para que la web nunca muestre un reparto distinto al que usa el motor.
 */
export type PerfilId = "conservador" | "moderado" | "moderado_agresivo" | "agresivo";

export interface Perfil {
  id: PerfilId;
  nombre: string;
  descripcion: string;
  reparto: Record<"acciones_ar" | "cedears" | "bonos_usd" | "pesos" | "caja", number>;
}

export const PERFILES: readonly Perfil[] = [
  {
    id: "conservador",
    nombre: "Conservador",
    descripcion: "Prioriza no perder. Más bonos y pesos, menos acciones.",
    reparto: { acciones_ar: 0.15, cedears: 0.2, bonos_usd: 0.35, pesos: 0.25, caja: 0.05 },
  },
  {
    id: "moderado",
    nombre: "Moderado",
    descripcion: "Equilibrio entre crecer y cuidar. Mitad acciones, mitad renta fija.",
    reparto: { acciones_ar: 0.3, cedears: 0.3, bonos_usd: 0.2, pesos: 0.15, caja: 0.05 },
  },
  {
    id: "moderado_agresivo",
    nombre: "Medio agresivo",
    descripcion: "Apunta a crecer fuerte, con algo de bonos para amortiguar las caídas.",
    reparto: { acciones_ar: 0.3, cedears: 0.4, bonos_usd: 0.15, pesos: 0.1, caja: 0.05 },
  },
  {
    id: "agresivo",
    nombre: "Agresivo",
    descripcion: "Busca el máximo crecimiento y acepta caídas fuertes. Mayormente acciones.",
    reparto: { acciones_ar: 0.45, cedears: 0.35, bonos_usd: 0.1, pesos: 0.05, caja: 0.05 },
  },
] as const;

export const PERFIL_POR_DEFECTO: PerfilId = "moderado";

export function perfilPorId(id: string | null | undefined): Perfil | undefined {
  return PERFILES.find((p) => p.id === id);
}

export function nombrePerfil(id: string | null | undefined): string {
  return perfilPorId(id)?.nombre ?? "—";
}
