/**
 * Formas que escribe el motor (Python) en la base. Se validan con zod de forma tolerante: un campo raro no
 * rompe la pantalla, queda en null. Ver `src/servicio.py::_armar`, `src/store.py`, `src/operador/*`.
 */
import { z } from "zod";

const num = z.preprocess((v) => {
  if (typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v))) return Number(v);
  return v;
}, z.number().finite().nullable().optional()).catch(null);
const str = z.preprocess((v) => (v === null || v === undefined ? null : String(v)), z.string().nullable()).catch(null);
const bool = z.preprocess((v) => {
  if (v === "True" || v === "true" || v === 1) return true;
  if (v === "False" || v === "false" || v === 0) return false;
  return v;
}, z.boolean().nullable().optional()).catch(null);
const fracciones = z.record(z.string(), z.number()).catch({});

export const posicionSchema = z.looseObject({
  cantidad: num,
  precio: num,
  ppc: num,
  valorizado: num,
  tipo: str,
  moneda: str,
});
export type Posicion = z.infer<typeof posicionSchema>;

export const noticiaSchema = z.looseObject({ numero: num, fecha: str, texto: str, eventos: z.array(z.string()).catch([]) });
export const recomendacionSchema = z.looseObject({
  numero: num,
  fecha: str,
  fuente: str,
  ticker: str,
  rating: str,
  precio_objetivo_usd: num,
  horizonte: str,
});
export const contextoSchema = z.looseObject({
  noticias: z.array(noticiaSchema).catch([]),
  recomendaciones: z.array(recomendacionSchema).catch([]),
  eventos: z.array(z.string()).catch([]),
  upside_consenso: num,
  var_semana_adr: num,
});
export type Contexto = z.infer<typeof contextoSchema>;

export const macroSchema = z.looseObject({
  regimen: z.string().catch("sin datos"),
  score: num,
  riesgo_pais: num,
  riesgo_pais_cambio_60d: num,
  ccl: num,
  oficial: num,
  brecha: num,
  motivos: z.array(z.string()).catch([]),
});

export const tacticoSchema = z.looseObject({
  riesgo: num,
  motivos: z.array(z.string()).catch([]),
  sectores_favorecidos: z.array(z.string()).catch([]),
  sectores_castigados: z.array(z.string()).catch([]),
  eventos: z
    .array(z.looseObject({ nombre: str, fecha: str, dias_para_evento: num }))
    .catch([]),
  asignacion_base: fracciones.optional(),
  asignacion: fracciones.optional(),
});

export const reporteSemanalSchema = z.looseObject({
  numero: num,
  fecha: str,
  resumen: str,
  riesgo_pais: num,
  ccl: num,
  brecha_pct: num,
});

export const metaSchema = z.looseObject({
  fecha: str,
  horizonte: str,
  perfil: str,
  broker: str,
  macro: macroSchema.catch({ regimen: "sin datos", motivos: [] }),
  asignacion: fracciones,
  actual_por_clase: fracciones,
  cartera: z
    .looseObject({
      caja: num,
      valor_total: num,
      posiciones: z.record(z.string(), posicionSchema).catch({}),
    })
    .catch({ caja: null, valor_total: null, posiciones: {} }),
  reporte_semanal: reporteSemanalSchema.nullable().catch(null).optional(),
  contexto: z.record(z.string(), contextoSchema).catch({}).optional(),
  escala: z.record(z.string(), z.unknown()).nullable().catch(null).optional(),
  tactico: tacticoSchema.nullable().catch(null).optional(),
});
export type Meta = z.infer<typeof metaSchema>;

export const filaRankingSchema = z.looseObject({
  ticker: z.string(),
  tipo: str,
  panel: str,
  sector: str,
  score: num,
  senal: str,
  calidad_datos: str,
  score_tecnico: num,
  score_fundamental: num,
  tec_rel: num,
  fund_rel: num,
  precio_usd: num,
  precio_ars: num,
  rsi14: num,
  mom_3m: num,
  mom_6m: num,
  mom_12m_1m: num,
  vol_anual: num,
  dist_max_52s: num,
  sobre_sma200: bool,
  vol_ars_20d: num,
  liquido: bool,
  upside_consenso: num,
  eventos: str,
  alertas: str,
  en_cartera: bool,
  nota: str,
});
export type FilaRanking = z.infer<typeof filaRankingSchema>;

export const filaRentaFijaSchema = z.looseObject({
  ticker_iol: str,
  ticker: str,
  nombre: str,
  clase: str,
  moneda: str,
  emisor: str,
  ley: str,
  precio_ars: num,
  precio_usd: num,
  tir: num,
  tem: num,
  duration: num,
  vencimiento: str,
  dias: num,
  paridad: num,
  senal_rv: str,
  spread_vs_curva_pb: num,
  volumen_ars: num,
  score_rf: num,
  apto_compra: bool,
  motivo_no_apto: str,
  confianza: str,
});
export type FilaRentaFija = z.infer<typeof filaRentaFijaSchema> & { clave: string };

export const filaObjetivoSchema = z.looseObject({ ticker: str, clase: str, peso_objetivo: num, peso_actual: num });
export type FilaObjetivo = z.infer<typeof filaObjetivoSchema>;

export const filaOrdenSchema = z.looseObject({
  ticker: str,
  lado: str,
  cantidad: num,
  precio_ref: num,
  monto_ars: num,
  nota: str,
});
export type FilaOrden = z.infer<typeof filaOrdenSchema>;

/** Parsea una lista de filas descartando las que no tienen forma de fila. */
export function filas<T extends z.ZodType>(schema: T, raw: unknown): z.infer<T>[] {
  if (!Array.isArray(raw)) return [];
  const out: z.infer<T>[] = [];
  for (const r of raw) {
    const p = schema.safeParse(r);
    if (p.success) out.push(p.data);
  }
  return out;
}

// --- estado del operador ---------------------------------------------------
export const pausadoSchema = z.looseObject({ pausado: z.boolean(), motivo: str.optional() });
export const modoRealSchema = z.looseObject({ habilitado: z.boolean(), desde: str.optional() });
export const aportesModoSchema = z.looseObject({ total: num, caja: num, caja_ts: str.optional() });
export const aportesSchema = z.record(z.string(), aportesModoSchema).catch({});
export const seguimientoModoSchema = z.looseObject({
  indice: num,
  pico: num,
  valor: num,
  bm_indice: num,
  alertado: bool,
});
export const seguimientoSchema = z.record(z.string(), seguimientoModoSchema).catch({});
export const pedidoFondosSchema = z
  .looseObject({ monto: num, texto: str, recompras: z.array(z.string()).catch([]) })
  .nullable()
  .catch(null);

export type Modo = "paper" | "live";
export const modoSchema = z.enum(["paper", "live"]);
