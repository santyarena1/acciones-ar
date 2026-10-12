/** Textos del motor -> castellano llano (sin siglas internas, decimales con coma). */
import { NOMBRE } from "../labels";
import { plata } from "../format";

const REEMPLAZOS: [RegExp, string][] = [
  [/\(Solo informativo, la regla está apagada\)\s*/gi, ""],
  [/brecha CCL\/oficial/gi, "diferencia entre el dólar bolsa y el oficial"],
  [/(\d+(?:[.,]\d+)?)\s*pb\b/g, "$1 puntos"],
  [/Merval en USD/g, "La bolsa argentina medida en dólares"],
  [/media de 200 ruedas/gi, "promedio de los últimos 10 meses"],
  [/tendencia de 200 ruedas/gi, "tendencia de los últimos 10 meses"],
  [/momentum ajustado por riesgo/gi, "subas recientes, ajustadas por riesgo"],
  [/\bCCL\b/g, "dólar bolsa"],
];

/** Pasa "6.4%" a "6,4%" sin tocar fechas ISO ni montos con miles. */
function comaDecimal(s: string): string {
  return s.replace(/(\d)\.(\d+)%/g, "$1,$2%");
}

export function humanizar(texto: string): string {
  let s = texto;
  for (const [re, rep] of REEMPLAZOS) s = s.replace(re, rep);
  s = comaDecimal(s.trim());
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function esSoloInformativo(texto: string): boolean {
  return /solo informativo/i.test(texto) || /solo aviso/i.test(texto);
}

/** Fechas ISO dentro de un texto -> dd/mm. */
export function fechasCortas(texto: string): string {
  return texto.replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g, "$3/$2");
}

/** Pedido de fondos del motor -> frase propia con montos es-AR y nombres legibles. */
export function textoPedidoFondos(monto: number | null | undefined, recompras: string[]): string {
  const base = `Para cumplir el plan completo faltan ${plata(monto)}.`;
  if (!recompras.length) return base + " Si podés, transferí esa plata a tu cuenta.";
  const lindas = recompras.map((r) =>
    comaDecimal(r.replace(/^([A-Z0-9]+)\s/, (_m, t: string) => `${NOMBRE[t] ?? t} `)).replace(/(−|-)(\d+)%/, "−$2%"),
  );
  return `${base} Buenas oportunidades para sumar: ${lindas.join("; ")}.`;
}

/** "REVISAR STOP: -36% desde el máximo de 52 semanas y bajo la SMA200" -> castellano llano. */
export function alertaLegible(a: string): string {
  return a
    .replace(/REVISAR STOP:\s*/i, "Ojo: ")
    .replace(/(-?\d+)% desde el máximo de 52 semanas/, (_m, n: string) => `cayó ${n.replace("-", "")}% desde su máximo del último año`)
    .replace(/y bajo la SMA200/i, "y viene en baja")
    .replace(/volatilidad alta/i, "se mueve mucho (volátil)");
}
