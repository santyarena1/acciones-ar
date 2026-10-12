/** Respuestas del bot de Telegram (puras: reciben los datos ya leídos y devuelven texto HTML de Telegram). */
import type { Corrida } from "./corrida";
import { tenencias } from "./cartera";
import { describirEvento, type Evento } from "./eventos";
import type { EstadoOperador } from "./estado";
import { rendimiento } from "./estado";
import type { Modo } from "./schemas";
import { haceCuanto, hora, pct, plata, pp } from "../format";

export type ComandoBot = "estado" | "cartera" | "hoy" | "pausar" | "reanudar" | "revisar" | "ayuda";

const ALIAS: Record<string, ComandoBot> = {
  estado: "estado",
  cartera: "cartera",
  hoy: "hoy",
  pausar: "pausar",
  pausa: "pausar",
  reanudar: "reanudar",
  seguir: "reanudar",
  revisar: "revisar",
  ayuda: "ayuda",
  start: "ayuda",
  help: "ayuda",
};

/** "/estado@MiBot argumentos" -> "estado". Texto que no es comando -> null. */
export function parsearComando(texto: string | undefined): ComandoBot | null {
  const m = /^\/([a-zA-ZñÑ]+)(?:@\w+)?(?:\s|$)/.exec((texto ?? "").trim());
  if (!m?.[1]) return null;
  return ALIAS[m[1].toLowerCase()] ?? null;
}

export function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export const AYUDA = [
  "<b>Lo que te puedo contestar</b>",
  "/estado — cuánto vale tu cartera y cómo viene",
  "/cartera — qué tenés",
  "/hoy — lo que hice hoy",
  "/pausar — dejo de comprar y vender",
  "/reanudar — vuelvo a trabajar",
  "/revisar — reviso ahora",
  "/ayuda — esta lista",
].join("\n");

export function textoEstado(ctx: { modo: Modo; estado: EstadoOperador; corrida: Corrida | null; ultimaRevision: string | null }): string {
  const { modo, estado, corrida: c } = ctx;
  const lineas = [`<b>${estado.pausado ? "⏸ En pausa" : "▶ Activo"}</b> · ${modo === "live" ? "cuenta REAL" : "práctica"}`];
  if (!c) return [...lineas, "Todavía no hice ninguna revisión."].join("\n");
  const r = rendimiento(estado, modo, c.meta.cartera.valor_total);
  lineas.push(`Tu cartera vale <b>${esc(plata(r.valor))}</b>`);
  if (r.ganancia !== null) lineas.push(`Ganancia: ${esc(plata(r.ganancia, { signo: true }))} (${esc(pct(r.gananciaPct, { signo: true }))}) sobre ${esc(plata(r.aportado))}`);
  if (r.diferencia !== null) lineas.push(`Contra no hacer nada: ${esc(pp(r.diferencia))}`);
  lineas.push(`Efectivo: ${esc(plata(c.meta.cartera.caja))}`);
  if (estado.pedidoFondos?.monto) lineas.push(`💰 Para el plan completo faltan ${esc(plata(estado.pedidoFondos.monto))}.`);
  lineas.push(`<i>Última revisión ${esc(haceCuanto(ctx.ultimaRevision ?? c.creada))}.</i>`);
  return lineas.join("\n");
}

export function textoCartera(c: Corrida | null): string {
  if (!c) return "Todavía no tengo cartera: no hice ninguna revisión.";
  const t = tenencias(c);
  if (!t.length) return `Por ahora todo está en efectivo: ${esc(plata(c.meta.cartera.caja))}.`;
  const filas = t.slice(0, 15).map((x) => {
    const g = x.ganancia !== null ? ` (${esc(pct(x.ganancia, { signo: true }))})` : "";
    return `• ${esc(x.nombre)}: ${esc(plata(x.valor))}${g}`;
  });
  const extra = t.length > 15 ? [`…y ${t.length - 15} más.`] : [];
  return ["<b>Tu cartera</b>", ...filas, ...extra, `Efectivo: ${esc(plata(c.meta.cartera.caja))}`].join("\n");
}

export function textoHoy(eventos: Evento[], nombres?: Record<string, string>): string {
  if (!eventos.length) return "Hoy todavía no compré ni vendí nada.";
  const filas = [...eventos].reverse().map((e) => {
    const d = describirEvento(e, nombres);
    return `${esc(hora(e.ts))} · ${esc(d.titulo)}${d.detalle ? ` — ${esc(d.detalle)}` : ""}`;
  });
  return ["<b>Lo de hoy</b>", ...filas.slice(-20)].join("\n");
}
