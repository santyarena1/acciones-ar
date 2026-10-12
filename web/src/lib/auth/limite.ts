/**
 * Límite de intentos de ingreso. Puro: recibe los intentos fallidos recientes y decide.
 * Por IP: 5 en 15 min. Global (todas las IP): 30 en 15 min, para frenar ataques distribuidos sin dejar al dueño
 * afuera para siempre (la ventana se renueva sola).
 */
export const VENTANA_MS = 15 * 60 * 1000;
export const MAX_POR_IP = 5;
export const MAX_GLOBAL = 30;

export interface IntentoFallido {
  ip: string;
  ts: number;
}

export interface Veredicto {
  permitido: boolean;
  reintentarEnMin: number;
}

export function evaluarIntentos(intentos: readonly IntentoFallido[], ip: string, ahora = Date.now()): Veredicto {
  const recientes = intentos.filter((i) => ahora - i.ts < VENTANA_MS);
  const deIp = recientes.filter((i) => i.ip === ip);
  const bloqueante =
    deIp.length >= MAX_POR_IP ? deIp : recientes.length >= MAX_GLOBAL ? recientes : null;
  if (!bloqueante) return { permitido: true, reintentarEnMin: 0 };
  const masViejo = Math.min(...bloqueante.map((i) => i.ts));
  return { permitido: false, reintentarEnMin: Math.max(1, Math.ceil((masViejo + VENTANA_MS - ahora) / 60_000)) };
}
