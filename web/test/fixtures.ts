/** Corrida sintética con la forma exacta que escribe el motor (records con ticker / ticker_iol, NaN -> null). */
import type { CorridaCruda } from "@/lib/domain/corrida";

export const corridaCruda: CorridaCruda = {
  stamp: "20261011_2325",
  creada: "2026-10-12T02:25:00.000Z",
  modo: "paper",
  guia: "",
  meta: {
    fecha: "2026-10-11T23:25",
    horizonte: "mediano",
    perfil: "moderado_agresivo",
    broker: "paper",
    macro: { regimen: "neutral", riesgo_pais: 589, brecha: 0.0636, motivos: ["Riesgo país 589 pb", "brecha CCL/oficial 6.4%"] },
    asignacion: { acciones_ar: 0.3, cedears: 0.4, bonos_usd: 0.15, pesos: 0.1, caja: 0.05 },
    actual_por_clase: { caja: 0.25, acciones_ar: 0.35, cedears: 0.2, bonos_usd: 0.2 },
    cartera: {
      caja: 250000,
      valor_total: 1000000,
      posiciones: {
        YPFD: { cantidad: 10, precio: 35000, ppc: 30000, valorizado: 350000, tipo: "accion" },
        SPY: { cantidad: 10, precio: 20000, ppc: 20000, valorizado: 200000, tipo: "accion" },
        AN29: { cantidad: 150, precio: 133000, ppc: 140000, valorizado: 199500, tipo: "bono" },
        VACIA: { cantidad: 0, precio: 1, ppc: 1, valorizado: 0, tipo: "accion" },
      },
    },
    reporte_semanal: { numero: 214, fecha: "2026-10-05", resumen: "Semana de caídas." },
    contexto: {
      YPFD: {
        noticias: [{ numero: 214, fecha: "2026-10-05", texto: "Récord de producción.", eventos: [] }],
        recomendaciones: [{ numero: 214, fecha: "2026-10-05", fuente: "Allaria", ticker: "YPF", rating: "Comprar", precio_objetivo_usd: null, horizonte: null }],
        eventos: [],
        upside_consenso: 0.21,
        var_semana_adr: -3,
      },
    },
    escala: { posicion_minima: 40000 },
    tactico: { riesgo: 0, motivos: ["(Solo informativo, la regla está apagada) Vienen mejor: Energía"] },
  },
  ranking: [
    { ticker: "YPFD", tipo: "accion", sector: "energia", score: 70, senal: "AGREGAR", tec_rel: 84, sobre_sma200: true, fund_rel: null, upside_consenso: 0.21, rsi14: 55, precio_ars: 35000, alertas: "", en_cartera: true, mom_6m: 0.1 },
    { ticker: "SPY", tipo: "cedear", sector: "etf_indices", score: 81, senal: "COMPRAR", tec_rel: 60, sobre_sma200: true, precio_ars: 21000, alertas: "", en_cartera: true, mom_6m: 0.08 },
    { ticker: "XLE", tipo: "cedear", sector: "etf_sector", score: 93.6, senal: "COMPRAR", tec_rel: 86.8, sobre_sma200: true, precio_ars: 52450, alertas: null, en_cartera: false, mom_6m: 0.158 },
    { ticker: "GGAL", tipo: "accion", sector: "bancos", score: 35, senal: "REDUCIR / VENDER", tec_rel: 10, sobre_sma200: false, precio_ars: 5969, alertas: "REVISAR STOP: -37% desde el máximo de 52 semanas y bajo la SMA200", en_cartera: false, mom_6m: -0.2 },
    { ticker: "BAD", tipo: "cedear", score: "no-num", senal: null },
    { sin_ticker: true },
  ],
  rentaFija: [
    { ticker_iol: "AN29", ticker: "AN29", nombre: "Bonar 2029N", clase: "soberano_usd", tir: 0.122, duration: 2.5, vencimiento: "2029-11-30", precio_ars: 133000, senal_rv: "en_curva", score_rf: 81, apto_compra: true },
    { ticker_iol: "S29E7", ticker: "S29E7", nombre: "Lecap ene-27", clase: "lecap", tir: 0.266, duration: 0.25, vencimiento: "2027-01-29", precio_ars: 104.15, senal_rv: "caro", score_rf: 73, apto_compra: true },
    { ticker_iol: "TZX26", ticker: "TZX26", nombre: "Boncer jun-26", clase: "cer", tir: null, duration: null, score_rf: null, apto_compra: false, motivo_no_apto: "poco volumen" },
  ],
  objetivos: [
    { ticker: "SPY", clase: "cedears", peso_objetivo: 0.1, peso_actual: 0.2 },
    { ticker: "AN29", clase: "bonos_usd", peso_objetivo: 0.15, peso_actual: 0.2 },
  ],
  ordenes: [{ ticker: "SPY", lado: "COMPRAR", cantidad: 1, precio_ref: 20970, monto_ars: 20970, nota: null }],
};
