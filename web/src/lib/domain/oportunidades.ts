/** Filas unificadas para la tabla de oportunidades (acciones, CEDEARs, bonos y letras). Puro. */
import { esNumero } from "../format";
import { CLASE_RF, SECTOR, SENAL, nombre, tonoSenal } from "../labels";
import type { Corrida } from "./corrida";
import { capitalizar, razones } from "./razones";

export type Grupo = "ar" | "cedear" | "rf";

export interface FilaOportunidad {
  ticker: string;
  nombre: string;
  grupo: Grupo;
  que: string;
  puntaje: number | null;
  senal: string;
  tono: "sube" | "baja" | "neutro";
  precio: number | null;
  /** Acciones: suba en 6 meses (USD). Renta fija: rendimiento anual (TIR). */
  dato: number | null;
  enCartera: boolean;
}

export function filasOportunidades(c: Corrida): FilaOportunidad[] {
  const enCartera = new Set(Object.keys(c.meta.cartera.posiciones ?? {}));
  const rv: FilaOportunidad[] = c.ranking.map((f) => {
    const grupo: Grupo = f.tipo === "cedear" ? "cedear" : "ar";
    return {
      ticker: f.ticker,
      nombre: nombre(f.ticker),
      grupo,
      que: f.sector ? SECTOR[f.sector] ?? (grupo === "cedear" ? "CEDEAR" : "Acción argentina") : grupo === "cedear" ? "CEDEAR" : "Acción argentina",
      puntaje: f.score ?? null,
      senal: f.senal ? SENAL[f.senal] ?? "—" : "—",
      tono: tonoSenal(f.senal),
      precio: f.precio_ars ?? null,
      dato: f.mom_6m ?? null,
      enCartera: Boolean(f.en_cartera) || enCartera.has(f.ticker),
    };
  });
  const rf: FilaOportunidad[] = c.rentaFija.map((f) => {
    const apto = f.apto_compra !== false && esNumero(f.score_rf);
    return {
      ticker: f.clave,
      nombre: f.nombre ?? f.clave,
      grupo: "rf",
      que: f.clase ? CLASE_RF[f.clase] ?? "Renta fija" : "Renta fija",
      puntaje: f.score_rf ?? null,
      senal: !apto ? "No apto" : (f.score_rf ?? 0) >= 70 ? "Buena opción" : "Neutral",
      tono: !apto ? "neutro" : (f.score_rf ?? 0) >= 70 ? "sube" : "neutro",
      precio: f.precio_ars ?? null,
      dato: f.tir ?? null,
      enCartera: enCartera.has(f.clave),
    };
  });
  return [...rv, ...rf];
}

export interface Destacada {
  ticker: string;
  nombre: string;
  que: string;
  puntaje: number;
  frase: string;
  mom6m: number | null;
  enCartera: boolean;
}

/**
 * Las mejores ideas del momento: CEDEARs con señal de compra (las acciones argentinas no se eligen por puntaje:
 * el operador las tiene parejas).
 */
export function destacadas(c: Corrida, n = 4): Destacada[] {
  return c.ranking
    .filter((f) => f.senal === "COMPRAR" && f.tipo === "cedear" && esNumero(f.score))
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0, n)
    .map((f) => {
      const r = razones(f);
      return {
        ticker: f.ticker,
        nombre: nombre(f.ticker),
        que: f.sector ? SECTOR[f.sector] ?? "CEDEAR" : "CEDEAR",
        puntaje: f.score as number,
        frase: r.length ? capitalizar(r.join("; ")) + "." : "El modelo la ve bien en general.",
        mom6m: f.mom_6m ?? null,
        enCartera: Boolean(f.en_cartera),
      };
    });
}
