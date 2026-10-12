/** Eventos de la bitácora del operador -> frases en castellano llano. */
import { esNumero, numero, plata } from "../format";
import { MODO, nombre } from "../labels";

export interface Evento {
  id: number;
  ts: string;
  modo: string | null;
  tipo: string;
  datos: Record<string, unknown>;
}

export type TonoEvento = "compra" | "venta" | "plata" | "alerta" | "error" | "info" | "tenue";

export interface EventoLegible {
  titulo: string;
  detalle?: string;
  tono: TonoEvento;
  monto?: number | null;
}

/** Tipos que se muestran en el historial (el resto es interno: intentos, fotos, candados, logins). */
export const TIPOS_VISIBLES = [
  "orden",
  "aporte",
  "pedido_fondos",
  "descartada",
  "error",
  "pausa",
  "reanudar",
  "aviso_caida",
  "modo_real",
  "cancelacion",
  "corrida",
  "comando",
  "ajuste_aportes",
] as const;

/** Lo que cuenta como "movimiento" en el inicio. */
export const TIPOS_MOVIMIENTO = ["orden", "aporte"] as const;

const s = (x: unknown): string | null => (typeof x === "string" && x.trim() ? x : null);
const n = (x: unknown): number | null => {
  const v = typeof x === "string" ? Number(x) : x;
  return esNumero(v) ? v : null;
};

const ESTADOS_FALLIDOS = new Set(["rechazada", "error"]);

function orden(d: Record<string, unknown>, nombres?: Record<string, string>): EventoLegible {
  const ticker = s(d.ticker) ?? "?";
  const compra = d.lado === "COMPRAR";
  const cant = n(d.cantidad);
  const precio = n(d.precio);
  const mult = n(d.mult) ?? 1;
  const monto = cant !== null && precio !== null ? cant * precio * mult : null;
  const quien = nombre(ticker, nombres);
  const unidades = cant !== null ? `${numero(cant)} ${mult !== 1 ? "nominales" : cant === 1 ? "unidad" : "unidades"}` : "";
  if (ESTADOS_FALLIDOS.has(String(d.estado))) {
    return {
      titulo: `No pudo ${compra ? "comprar" : "vender"} ${quien}`,
      detalle: s(d.mensaje) ?? "El broker rechazó la orden.",
      tono: "error",
      monto: null,
    };
  }
  return {
    titulo: `${compra ? "Compró" : "Vendió"} ${quien}`,
    detalle: [unidades, monto !== null ? `por ${plata(monto)}` : null].filter(Boolean).join(" "),
    tono: compra ? "compra" : "venta",
    monto: monto === null ? null : compra ? -monto : monto,
  };
}

export function describirEvento(e: Evento, nombres?: Record<string, string>): EventoLegible {
  const d = e.datos ?? {};
  switch (e.tipo) {
    case "orden":
      return orden(d, nombres);
    case "aporte": {
      const monto = n(d.monto) ?? 0;
      if (d.inicial) return { titulo: "Capital inicial", detalle: `Arrancó con ${plata(monto)}`, tono: "plata", monto };
      return monto >= 0
        ? { titulo: "Detectó un depósito", detalle: `Ingresaste ${plata(monto)}. Lo invierte según el plan.`, tono: "plata", monto }
        : { titulo: "Detectó un retiro", detalle: `Sacaste ${plata(Math.abs(monto))}. Ajusta la cartera a lo que queda.`, tono: "plata", monto };
    }
    case "ajuste_aportes":
      return { titulo: "Corregiste el total que pusiste", detalle: `Ahora: ${plata(n(d.total))}`, tono: "info" };
    case "pedido_fondos":
      return {
        titulo: "Pidió más plata",
        detalle: s(d.texto) ?? `Para el plan completo faltan ${plata(n(d.monto))}.`,
        tono: "alerta",
      };
    case "descartada":
      return {
        titulo: `No operó ${nombre(s(d.ticker) ?? "?", nombres)}`,
        detalle: "El precio en vivo se alejó demasiado del analizado. Es una protección: lo vuelve a mirar en la próxima revisión.",
        tono: "tenue",
      };
    case "error":
      return {
        titulo: "Algo falló y no operó en esta revisión",
        detalle: "Lo vuelve a intentar en la próxima. Si se repite, avisale a quien te ayuda con el sistema.",
        tono: "error",
      };
    case "pausa":
      return { titulo: "Se pausó el operador", detalle: s(d.motivo) && d.motivo !== "manual" ? String(d.motivo) : undefined, tono: "alerta" };
    case "reanudar":
      return { titulo: "Se reactivó el operador", tono: "info" };
    case "aviso_caida":
      return { titulo: "Aviso de caída fuerte", detalle: s(d.texto) ?? undefined, tono: "alerta" };
    case "modo_real":
      return d.habilitado === false
        ? { titulo: "Volvió a modo práctica", detalle: "Ya no opera con tu cuenta real de IOL.", tono: "info" }
        : { titulo: "Se activó el modo real", detalle: "Desde ahora opera con tu cuenta de IOL.", tono: "alerta" };
    case "cancelacion":
      return { titulo: "Canceló una orden que había quedado pendiente", detalle: s(d.simbolo) ? nombre(String(d.simbolo), nombres) : undefined, tono: "tenue" };
    case "corrida": {
      const k = n(d.ordenes) ?? 0;
      if (d.solo_analisis) {
        return { titulo: "Revisó el mercado (fuera de horario: solo analizó, no operó)", tono: "tenue" };
      }
      return {
        titulo: k ? `Revisó la cartera e hizo ${k} ${k === 1 ? "operación" : "operaciones"}` : "Revisó la cartera: no hacía falta operar",
        detalle: n(d.valor_total) !== null ? `Valor en ese momento: ${plata(n(d.valor_total))}` : undefined,
        tono: "tenue",
      };
    }
    case "comando":
      return describirComando(d);
    default:
      return { titulo: "Evento del operador", tono: "tenue" };
  }
}

export function etiquetaModo(modo: string | null | undefined): string | null {
  return modo ? MODO[modo] ?? null : null;
}

const NOMBRE_COMANDO: Record<string, string> = {
  depositar_practica: "Sumó plata a la cuenta de práctica",
  reiniciar_practica: "Reinició la práctica desde cero",
  revisar: "Hizo la revisión que pediste",
};

/** Pedidos de la web ya procesados por el motor ({comando, id_comando, resultado}) o avisos de la app ({texto}). */
function describirComando(d: Record<string, unknown>): EventoLegible {
  if (typeof d.texto === "string") return { titulo: d.texto, tono: "info" };
  const cmd = s(d.comando) ?? "";
  const r = (typeof d.resultado === "object" && d.resultado !== null ? d.resultado : {}) as Record<string, unknown>;
  if (r.ok === false) {
    return { titulo: "No pudo hacer lo que pediste desde la app", detalle: NOMBRE_COMANDO[cmd] ? `Pedido: ${NOMBRE_COMANDO[cmd]!.toLowerCase()}.` : undefined, tono: "error" };
  }
  const monto = n(r.monto) ?? n(r.capital);
  return {
    titulo: NOMBRE_COMANDO[cmd] ?? "Atendió un pedido desde la app",
    detalle: monto !== null ? plata(monto) : undefined,
    tono: cmd === "depositar_practica" ? "plata" : "info",
  };
}
