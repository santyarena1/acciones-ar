/** Cartera valuada: qué tenés, cuánto vale, cuánto ganás y por qué está. Port de `app/comun.py::tabla_cartera`. */
import { esNumero } from "../format";
import { CLASE_RF, TIPO, nombre, type ClaseCartera } from "../labels";
import type { Corrida } from "./corrida";
import { porQue } from "./razones";

const CLASE_RF_A_CARTERA: Record<string, ClaseCartera> = {
  soberano_usd: "bonos_usd",
  on_usd: "bonos_usd",
  lecap: "pesos",
  boncap: "pesos",
  cer: "pesos",
  dual: "pesos",
};
const TIPO_A_CLASE: Record<string, ClaseCartera> = {
  accion: "acciones_ar",
  cedear: "cedears",
  letra: "pesos",
  bono: "bonos_usd",
  on: "bonos_usd",
};
const TIPOS_RF = new Set(["bono", "letra", "on"]);

export interface Tenencia {
  ticker: string;
  nombre: string;
  que: string;
  clase: ClaseCartera;
  cantidad: number;
  precio: number | null;
  costo: number | null;
  valor: number;
  ganancia: number | null;
  peso: number;
  porque: string;
  alerta: string | null;
  senal: string | null;
  esRentaFija: boolean;
}

export function claseDe(c: Corrida, ticker: string, tipoPosicion?: string | null): ClaseCartera {
  const obj = c.objetivoPorTicker.get(ticker)?.clase;
  if (obj && obj in { acciones_ar: 1, cedears: 1, bonos_usd: 1, pesos: 1, oro: 1, caja: 1 }) return obj as ClaseCartera;
  const rf = c.rfPorTicker.get(ticker);
  if (rf?.clase) return CLASE_RF_A_CARTERA[rf.clase] ?? "bonos_usd";
  const tipo = c.porTicker.get(ticker)?.tipo ?? tipoPosicion ?? "accion";
  return TIPO_A_CLASE[tipo] ?? "acciones_ar";
}

function precioActual(c: Corrida, t: string): number | null {
  const r = c.porTicker.get(t)?.precio_ars;
  if (esNumero(r)) return r;
  const rf = c.rfPorTicker.get(t)?.precio_ars;
  return esNumero(rf) ? rf : null;
}

export function tenencias(c: Corrida): Tenencia[] {
  const pos = c.meta.cartera.posiciones ?? {};
  const out: Omit<Tenencia, "peso">[] = [];
  for (const [t, p] of Object.entries(pos)) {
    const cantidad = esNumero(p.cantidad) ? p.cantidad : 0;
    if (cantidad <= 0) continue;
    const rf = c.rfPorTicker.get(t) ?? null;
    const r = c.porTicker.get(t) ?? null;
    const esRf = Boolean(rf) || TIPOS_RF.has(p.tipo ?? "");
    const mult = esRf ? 0.01 : 1;
    const precio = precioActual(c, t) ?? (esNumero(p.precio) ? p.precio : null);
    const costo = esNumero(p.ppc) && p.ppc > 0 ? p.ppc : null;
    const valor = cantidad * (precio ?? 0) * mult;
    const que = rf?.clase
      ? CLASE_RF[rf.clase] ?? "Renta fija"
      : TIPO[r?.tipo ?? p.tipo ?? ""] ?? (esRf ? "Renta fija" : "Activo");
    out.push({
      ticker: t,
      nombre: nombre(t, c.nombresRf),
      que,
      clase: claseDe(c, t, p.tipo),
      cantidad,
      precio,
      costo,
      valor,
      ganancia: costo && precio ? precio / costo - 1 : null,
      porque: porQue({ ranking: r, rentaFija: rf }),
      alerta: r?.alertas?.trim() ? r.alertas.trim() : null,
      senal: r?.senal ?? null,
      esRentaFija: esRf,
    });
  }
  const total = esNumero(c.meta.cartera.valor_total) && c.meta.cartera.valor_total > 0
    ? c.meta.cartera.valor_total
    : out.reduce((a, b) => a + b.valor, 0);
  return out
    .map((x) => ({ ...x, peso: total ? x.valor / total : 0 }))
    .sort((a, b) => b.valor - a.valor);
}

export interface RepartoClase {
  clase: ClaseCartera;
  actual: number;
  objetivo: number;
}

/** Reparto actual vs. objetivo por clase, en el orden fijo de clases (el color sigue a la clase). */
export function reparto(c: Corrida, orden: readonly ClaseCartera[]): RepartoClase[] {
  const actual = c.meta.actual_por_clase ?? {};
  const objetivo = c.meta.asignacion ?? {};
  return orden
    .map((clase) => ({ clase, actual: actual[clase] ?? 0, objetivo: objetivo[clase] ?? 0 }))
    .filter((r) => r.actual > 0.0005 || r.objetivo > 0.0005);
}
