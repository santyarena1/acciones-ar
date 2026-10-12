/**
 * Por qué el modelo ve bien (o mal) un activo, en frases cortas. Misma lógica y umbrales que `src/guia.py::razones`,
 * con el texto pasado a castellano llano (sin "momentum", "SMA200" ni "RSI").
 */
import { esNumero, mesAnio, numero, pct } from "../format";
import { CLASE_RF, SENAL } from "../labels";
import type { FilaRanking, FilaRentaFija } from "./schemas";

export type FilaRazones = Pick<FilaRanking, "tec_rel" | "sobre_sma200" | "fund_rel" | "upside_consenso" | "rsi14">;

export function razones(f: Partial<FilaRazones>): string[] {
  const r: string[] = [];
  const { tec_rel, fund_rel, upside_consenso, rsi14, sobre_sma200 } = f;
  if (esNumero(tec_rel) && tec_rel >= 75) r.push(`viene subiendo más que el ${numero(tec_rel)}% de lo que analiza`);
  else if (esNumero(tec_rel) && tec_rel <= 25) r.push("viene entre las que menos suben de lo que analiza");
  if (sobre_sma200 === true) r.push("en alza: está por encima de su promedio de los últimos 10 meses, en dólares");
  else if (sobre_sma200 === false) r.push("en baja: está por debajo de su promedio de los últimos 10 meses, en dólares");
  if (esNumero(fund_rel) && fund_rel >= 70) r.push(`sus números (ganancias, deuda, valuación) son mejores que los del ${numero(fund_rel)}% de su grupo`);
  else if (esNumero(fund_rel) && fund_rel <= 30) r.push("sus números (ganancias, deuda, valuación) son flojos frente a su grupo");
  if (esNumero(upside_consenso) && Math.abs(upside_consenso) >= 0.1)
    r.push(`los analistas le ven un precio ${pct(upside_consenso, { signo: true, decimales: 0 })} respecto de hoy`);
  if (esNumero(rsi14) && rsi14 > 75) r.push(`subió muy rápido en las últimas semanas (puede frenar)`);
  return r;
}

/** Igual que `TEXTO_RAZON` del motor (src/portfolio/equiponderado.py). */
export const TEXTO_PAREJA = "cartera pareja de las más líquidas del panel líder";

export function capitalizar(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

/** Frase completa de por qué el operador tiene (o quiere) un activo. */
export function porQue(opts: {
  ranking?: FilaRanking | null;
  rentaFija?: FilaRentaFija | null;
  estrategiaAr?: "equiponderado" | "score";
}): string {
  const { ranking: r, rentaFija: rf, estrategiaAr = "equiponderado" } = opts;
  if (r) {
    if (r.tipo === "accion" && estrategiaAr === "equiponderado") {
      const extra = razones(r);
      return (
        "Es una de las acciones más líquidas del panel líder: el operador las tiene a todas en partes iguales" +
        (extra.length ? `. Además: ${extra.join("; ")}.` : ".")
      );
    }
    const mot = razones(r);
    const senal = r.senal ? SENAL[r.senal] ?? r.senal : null;
    if (!mot.length) return "Sigue dentro de lo que busca el operador" + (senal ? ` (señal: ${senal.toLowerCase()}).` : ".");
    return capitalizar(mot.join("; ")) + ".";
  }
  if (rf) {
    const que = rf.clase ? CLASE_RF[rf.clase] ?? "Renta fija" : "Renta fija";
    const tir = esNumero(rf.tir) ? `rinde ${pct(rf.tir)} por año` : "paga intereses";
    const vto = rf.vencimiento ? ` si se mantiene hasta que vence (${mesAnio(rf.vencimiento)})` : "";
    return `${que}: ${tir}${vto}.`;
  }
  return "Lo tiene para completar el reparto que pide tu perfil.";
}
