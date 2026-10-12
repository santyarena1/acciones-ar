/** Formatos es-AR determinísticos (no dependen del ICU del servidor): $ 1.234.567 · 12,3% · 12/10 14:30. */

export const TZ = "America/Argentina/Buenos_Aires";

export function esNumero(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x);
}

function agrupar(entero: string): string {
  return entero.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

/** Número con separador de miles "." y decimales ",". */
export function numero(x: unknown, decimales = 0): string {
  if (!esNumero(x)) return "—";
  const abs = Math.abs(x);
  const [ent = "0", dec] = abs.toFixed(decimales).split(".");
  const cero = Number(abs.toFixed(decimales)) === 0;
  const signo = x < 0 && !cero ? "−" : "";
  return signo + agrupar(ent) + (dec ? "," + dec : "");
}

/** Plata en pesos: "$ 1.234.567". Con `signo`, agrega "+" a los positivos. */
export function plata(x: unknown, opts: { signo?: boolean; decimales?: number } = {}): string {
  if (!esNumero(x)) return "—";
  const n = numero(x, opts.decimales ?? 0);
  const neg = n.startsWith("−");
  const cuerpo = neg ? n.slice(1) : n;
  const s = neg ? "−" : opts.signo && Number(x.toFixed(opts.decimales ?? 0)) > 0 ? "+" : "";
  return `${s}$ ${cuerpo}`;
}

/** Plata abreviada para ejes y espacios chicos: "$ 1,2 M", "$ 850 mil". */
export function plataCorta(x: unknown): string {
  if (!esNumero(x)) return "—";
  const abs = Math.abs(x);
  const s = x < 0 ? "−" : "";
  if (abs >= 1e6) return `${s}$ ${numero(abs / 1e6, abs >= 1e7 ? 0 : 1)} M`;
  if (abs >= 1e3) return `${s}$ ${numero(abs / 1e3, 0)} mil`;
  return `${s}$ ${numero(abs, 0)}`;
}

/** Porcentaje desde fracción: 0.123 -> "12,3%". */
export function pct(x: unknown, opts: { signo?: boolean; decimales?: number } = {}): string {
  if (!esNumero(x)) return "—";
  const d = opts.decimales ?? 1;
  const v = x * 100;
  const n = numero(v, d);
  const positivo = Number(v.toFixed(d)) > 0;
  return `${opts.signo && positivo ? "+" : ""}${n}%`;
}

/** Puntos porcentuales para diferencias: 0.021 -> "+2,1 pp". */
export function pp(x: unknown): string {
  if (!esNumero(x)) return "—";
  return `${pct(x, { signo: true }).replace("%", "")} pp`;
}

export function tono(x: unknown, umbral = 0.0005): "sube" | "baja" | "neutro" {
  if (!esNumero(x) || Math.abs(x) < umbral) return "neutro";
  return x > 0 ? "sube" : "baja";
}

function partes(d: Date, o: Intl.DateTimeFormatOptions): Record<string, string> {
  const out: Record<string, string> = {};
  for (const p of new Intl.DateTimeFormat("es-AR", { timeZone: TZ, ...o }).formatToParts(d)) out[p.type] = p.value;
  return out;
}

export function aFecha(x: string | Date | null | undefined): Date | null {
  if (!x) return null;
  const d = x instanceof Date ? x : new Date(x);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "2026-10-12" en hora Argentina (para agrupar por día). */
export function diaAR(x: string | Date): string {
  const d = aFecha(x);
  if (!d) return "";
  const p = partes(d, { year: "numeric", month: "2-digit", day: "2-digit" });
  return `${p.year}-${p.month}-${p.day}`;
}

export function hora(x: string | Date | null | undefined): string {
  const d = aFecha(x);
  if (!d) return "—";
  const p = partes(d, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  return `${p.hour}:${p.minute}`;
}

/** "12/10" o "12/10/2025" si no es el año en curso. */
export function fechaCorta(x: string | Date | null | undefined, hoy = new Date()): string {
  const d = aFecha(x);
  if (!d) return "—";
  const p = partes(d, { year: "numeric", month: "2-digit", day: "2-digit" });
  const anio = partes(hoy, { year: "numeric" }).year;
  return p.year === anio ? `${p.day}/${p.month}` : `${p.day}/${p.month}/${p.year}`;
}

/** "lunes 12 de octubre". */
export function fechaLarga(x: string | Date | null | undefined): string {
  const d = aFecha(x);
  if (!d) return "—";
  const p = partes(d, { weekday: "long", day: "numeric", month: "long" });
  return `${p.weekday} ${p.day} de ${p.month}`;
}

/** Título de un día en el historial: "Hoy", "Ayer" o "lunes 12 de octubre". */
export function tituloDia(dia: string, ahora = new Date()): string {
  const hoy = diaAR(ahora);
  const ayer = diaAR(new Date(ahora.getTime() - 86_400_000));
  if (dia === hoy) return "Hoy";
  if (dia === ayer) return "Ayer";
  return fechaLarga(new Date(`${dia}T12:00:00-03:00`));
}

/** "hace 5 min", "hace 3 h", "hace 2 días". */
export function haceCuanto(x: string | Date | null | undefined, ahora = new Date()): string {
  const d = aFecha(x);
  if (!d) return "nunca";
  const min = Math.round((ahora.getTime() - d.getTime()) / 60_000);
  if (min < 1) return "recién";
  if (min < 60) return `hace ${min} min`;
  const h = Math.round(min / 60);
  if (h < 24) return `hace ${h} h`;
  const dias = Math.round(h / 24);
  return dias === 1 ? "ayer" : `hace ${dias} días`;
}

/** Fecha ISO de vencimiento -> "may. 2027". */
export function mesAnio(x: string | null | undefined): string {
  const d = aFecha(x ? `${x.slice(0, 10)}T12:00:00-03:00` : null);
  if (!d) return "—";
  const p = partes(d, { month: "short", year: "numeric" });
  return `${p.month} ${p.year}`;
}

/** Años con coma: 1.71 -> "1,7 años"; menos de un año -> meses. */
export function anios(x: unknown): string {
  if (!esNumero(x)) return "—";
  if (x < 1) {
    const m = Math.max(1, Math.round(x * 12));
    return `${m} ${m === 1 ? "mes" : "meses"}`;
  }
  return `${numero(x, 1)} años`;
}
