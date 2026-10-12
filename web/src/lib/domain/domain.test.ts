import { describe, expect, test } from "vitest";
import { corridaCruda } from "../../../test/fixtures";
import { ORDEN_CLASES, nombre, nombreCorto } from "../labels";
import { AYUDA, parsearComando, textoCartera, textoEstado, textoHoy } from "./bot";
import { reparto, tenencias } from "./cartera";
import { prepararCorrida } from "./corrida";
import { interpretarEstado, rendimiento } from "./estado";
import { describirEvento, type Evento } from "./eventos";
import { proximaRevision } from "./horario";
import { destacadas, filasOportunidades } from "./oportunidades";
import { mezclar, modoDe, perfilDe } from "./preferencias";
import { porQue, razones } from "./razones";
import { alertaLegible, esSoloInformativo, fechasCortas, humanizar, textoPedidoFondos } from "./textos";

const c = prepararCorrida(corridaCruda);

describe("prepararCorrida (validación tolerante)", () => {
  test("descarta filas sin ticker y deja en null los números rotos", () => {
    expect(c.ranking.map((f) => f.ticker)).toEqual(["YPFD", "SPY", "XLE", "GGAL", "BAD"]);
    expect(c.porTicker.get("BAD")?.score).toBeNull();
  });
  test("indexa renta fija por ticker_iol y arma nombres", () => {
    expect(c.rfPorTicker.get("AN29")?.tir).toBe(0.122);
    expect(c.nombresRf.S29E7).toBe("Lecap ene-27");
  });
  test("una meta vacía no rompe", () => {
    const v = prepararCorrida({ ...corridaCruda, meta: null, ranking: "x", rentaFija: null });
    expect(v.meta.cartera.posiciones).toEqual({});
    expect(v.ranking).toEqual([]);
    expect(v.meta.macro.regimen).toBe("sin datos");
  });
});

describe("tenencias y reparto", () => {
  const t = tenencias(c);
  test("valúa con el precio de hoy, bonos cada 100 nominales y ordena por valor", () => {
    expect(t.map((x) => x.ticker)).toEqual(["YPFD", "SPY", "AN29"]);
    const an29 = t.find((x) => x.ticker === "AN29")!;
    expect(an29.valor).toBeCloseTo(150 * 133000 * 0.01);
    expect(an29.clase).toBe("bonos_usd");
    expect(an29.que).toBe("Bono del Estado en dólares");
    expect(an29.ganancia).toBeCloseTo(133000 / 140000 - 1);
  });
  test("CEDEAR reconocido aunque el broker diga 'accion', con nombre humano", () => {
    const spy = t.find((x) => x.ticker === "SPY")!;
    expect(spy.clase).toBe("cedears");
    expect(spy.que).toBe("CEDEAR");
    expect(spy.nombre).toBe("S&P 500 (las 500 mayores de EE.UU.)");
    expect(spy.precio).toBe(21000);
    expect(spy.peso).toBeCloseTo(0.21);
  });
  test("acción local: razón de la cartera pareja", () => {
    expect(t[0]!.porque).toMatch(/más líquidas del panel líder/);
  });
  test("reparto en orden fijo de clases, sin clases vacías", () => {
    const r = reparto(c, ORDEN_CLASES);
    expect(r.map((x) => x.clase)).toEqual(["acciones_ar", "cedears", "bonos_usd", "pesos", "caja"]);
    expect(r.find((x) => x.clase === "pesos")).toEqual({ clase: "pesos", actual: 0, objetivo: 0.1 });
  });
});

describe("razones (port de src/guia.py)", () => {
  test("mismos umbrales que el motor", () => {
    expect(razones({ tec_rel: 75 })).toEqual(["viene subiendo más que el 75% de lo que analiza"]);
    expect(razones({ tec_rel: 74.9 })).toEqual([]);
    expect(razones({ tec_rel: 25 })[0]).toMatch(/menos suben/);
    expect(razones({ fund_rel: 70 })[0]).toMatch(/mejores que los del 70%/);
    expect(razones({ fund_rel: 30 })[0]).toMatch(/flojos/);
    expect(razones({ upside_consenso: 0.1 })[0]).toBe("los analistas le ven un precio +10% respecto de hoy");
    expect(razones({ upside_consenso: -0.099 })).toEqual([]);
    expect(razones({ rsi14: 76 })[0]).toMatch(/subió muy rápido/);
    expect(razones({ sobre_sma200: false })[0]).toMatch(/en baja/);
    expect(razones({ sobre_sma200: null })).toEqual([]);
  });
  test("sin jerga interna", () => {
    const todo = razones({ tec_rel: 90, sobre_sma200: true, fund_rel: 90, upside_consenso: 0.3, rsi14: 80 }).join(" ");
    expect(todo).not.toMatch(/momentum|SMA|RSI|ruedas|universo/);
  });
  test("porQue para CEDEAR, bono y fallback", () => {
    expect(porQue({ ranking: c.porTicker.get("XLE") })).toMatch(/^Viene subiendo/);
    expect(porQue({ rentaFija: c.rfPorTicker.get("AN29") })).toMatch(/rinde 12,2% por año si se mantiene hasta que vence/);
    expect(porQue({})).toMatch(/perfil/);
  });
});

describe("etiquetas", () => {
  test("nombres legibles", () => {
    expect(nombre("YPFD")).toBe("YPF");
    expect(nombre("S29E7", { S29E7: "Lecap ene-27" })).toBe("Lecap ene-27");
    expect(nombre("ZZZ")).toBe("ZZZ");
    expect(nombreCorto("SPY")).toBe("S&P 500");
  });
});

describe("oportunidades", () => {
  test("destacadas: solo CEDEARs con COMPRAR, por puntaje", () => {
    expect(destacadas(c).map((d) => d.ticker)).toEqual(["XLE", "SPY"]);
  });
  test("filas unificadas con señal humana y renta fija", () => {
    const f = filasOportunidades(c);
    expect(f.find((x) => x.ticker === "GGAL")).toMatchObject({ senal: "Vender", tono: "baja", grupo: "ar" });
    expect(f.find((x) => x.ticker === "AN29")).toMatchObject({ grupo: "rf", senal: "Buena opción", enCartera: true });
    expect(f.find((x) => x.ticker === "TZX26")?.senal).toBe("No apto");
  });
});

describe("estado del operador", () => {
  test("pausa ilegible = pausado (falla cerrado)", () => {
    expect(interpretarEstado({ pausado: { pausado: "si" } }).pausado).toBe(true);
    expect(interpretarEstado({}).pausado).toBe(false);
    expect(interpretarEstado({ pausado: { pausado: false, motivo: null } }).pausado).toBe(false);
  });
  test("modo real solo con habilitado true", () => {
    expect(interpretarEstado({ modo_real: { habilitado: "true" } }).modoReal.habilitado).toBe(false);
    expect(interpretarEstado({ modo_real: { habilitado: true, desde: "2026-10-12" } }).modoReal).toEqual({ habilitado: true, desde: "2026-10-12" });
  });
  test("rendimiento: valor − aportes y contra no hacer nada", () => {
    const e = interpretarEstado({
      aportes: { paper: { total: 800000, caja: 1, caja_ts: "x" } },
      seguimiento: { paper: { indice: 1.1, pico: 1.2, valor: 1, bm_indice: 1.05, alertado: false } },
      ultimo_pedido_fondos: { monto: 150000, texto: "x", recompras: [] },
    });
    const r = rendimiento(e, "paper", 1000000);
    expect(r.ganancia).toBe(200000);
    expect(r.gananciaPct).toBeCloseTo(0.25);
    expect(r.operador).toBeCloseTo(0.1);
    expect(r.noHacerNada).toBeCloseTo(0.05);
    expect(r.diferencia).toBeCloseTo(0.05);
    expect(r.caidaDesdeMaximo).toBeCloseTo(1.1 / 1.2 - 1);
    expect(e.pedidoFondos?.monto).toBe(150000);
    expect(rendimiento(e, "live", 1000000).ganancia).toBeNull();
  });
});

describe("preferencias", () => {
  test("mezcla profunda sin mutar", () => {
    const base = { operador: { perfil: "moderado", horizonte: "mediano" } };
    const out = mezclar(base, { operador: { modo: "live" } });
    expect(out).toEqual({ operador: { perfil: "moderado", horizonte: "mediano", modo: "live" } });
    expect(base).toEqual({ operador: { perfil: "moderado", horizonte: "mediano" } });
  });
  test("modo y perfil con defaults seguros", () => {
    expect(modoDe({})).toBe("paper");
    expect(modoDe({ operador: { modo: "LIVE" } })).toBe("paper");
    expect(modoDe({ operador: { modo: "live" } })).toBe("live");
    expect(perfilDe({ operador: { perfil: "inventado" } })).toBe("moderado");
    expect(perfilDe({ operador: { perfil: "agresivo" } })).toBe("agresivo");
  });
});

const ev = (tipo: string, datos: Record<string, unknown>): Evento => ({ id: 1, ts: "2026-10-12T14:30:00-03:00", modo: "paper", tipo, datos });

describe("eventos en castellano", () => {
  test("órdenes", () => {
    expect(describirEvento(ev("orden", { ticker: "YPFD", lado: "COMPRAR", cantidad: 6, precio: 8105, mult: 1, estado: "ejecutada (paper)" }))).toMatchObject({
      titulo: "Compró YPF",
      detalle: "6 unidades por $ 48.630",
      tono: "compra",
      monto: -48630,
    });
    const bono = describirEvento(ev("orden", { ticker: "AN29", lado: "VENDER", cantidad: 100, precio: 137000, mult: 0.01, estado: "ok" }), { AN29: "Bonar 2029N" });
    expect(bono).toMatchObject({ titulo: "Vendió Bonar 2029N", detalle: "100 nominales por $ 137.000", monto: 137000 });
    expect(describirEvento(ev("orden", { ticker: "GGAL", lado: "VENDER", estado: "rechazada", mensaje: "caja insuficiente" }))).toMatchObject({ titulo: "No pudo vender Grupo Galicia", tono: "error" });
  });
  test("aportes, pedidos, pausas, modo real, comandos y corridas", () => {
    expect(describirEvento(ev("aporte", { monto: 495236, inicial: true })).titulo).toBe("Capital inicial");
    expect(describirEvento(ev("aporte", { monto: 200000 })).detalle).toMatch(/Ingresaste \$ 200\.000/);
    expect(describirEvento(ev("aporte", { monto: -5000 })).titulo).toBe("Detectó un retiro");
    expect(describirEvento(ev("pedido_fondos", { monto: 1, texto: "faltan" })).tono).toBe("alerta");
    expect(describirEvento(ev("pausa", { motivo: "manual" })).detalle).toBeUndefined();
    expect(describirEvento(ev("modo_real", { habilitado: false })).titulo).toBe("Volvió a modo práctica");
    expect(describirEvento(ev("modo_real", { habilitado: true })).titulo).toBe("Se activó el modo real");
    expect(describirEvento(ev("comando", { comando: "depositar_practica", resultado: { ok: true, monto: 100000 } }))).toMatchObject({ titulo: "Sumó plata a la cuenta de práctica", detalle: "$ 100.000" });
    expect(describirEvento(ev("comando", { comando: "revisar", resultado: { ok: false, error: "x" } })).tono).toBe("error");
    expect(describirEvento(ev("corrida", { ordenes: 2, valor_total: 1000 })).titulo).toMatch(/hizo 2 operaciones/);
    expect(describirEvento(ev("corrida", { ordenes: 0, solo_analisis: true })).titulo).toMatch(/solo analizó/);
    expect(describirEvento(ev("error", { error: "KeyError: x" })).detalle).not.toMatch(/KeyError/);
    expect(describirEvento(ev("raro", {})).tono).toBe("tenue");
  });
});

describe("textos del motor", () => {
  test("humaniza jerga y decimales", () => {
    expect(humanizar("brecha CCL/oficial 6.4%")).toBe("Diferencia entre el dólar bolsa y el oficial 6,4%");
    expect(humanizar("Riesgo país 589 pb")).toBe("Riesgo país 589 puntos");
    expect(humanizar("(Solo informativo, la regla está apagada) Vienen mejor")).toBe("Vienen mejor");
    expect(esSoloInformativo("(Solo informativo, la regla está apagada) x")).toBe(true);
    expect(fechasCortas("el 2026-10-28")).toBe("el 28/10");
  });
  test("pedido de fondos y alertas", () => {
    expect(textoPedidoFondos(150000, [])).toMatch(/faltan \$ 150\.000/);
    expect(textoPedidoFondos(150000, ["GGAL (-12% desde su máximo, el análisis sigue positivo)"])).toMatch(/Grupo Galicia \(−12%/);
    expect(alertaLegible("REVISAR STOP: -37% desde el máximo de 52 semanas y bajo la SMA200")).toBe("Ojo: cayó 37% desde su máximo del último año y viene en baja");
  });
});

describe("próxima revisión (11:30 a 16:30, lun a vie, hora AR)", () => {
  test("antes de abrir, durante y después", () => {
    expect(proximaRevision(new Date("2026-10-12T09:00:00-03:00")).texto).toBe("hoy a las 11:30");
    expect(proximaRevision(new Date("2026-10-12T14:31:00-03:00")).texto).toBe("hoy a las 15:30");
    expect(proximaRevision(new Date("2026-10-12T17:00:00-03:00")).texto).toBe("mañana a las 11:30");
    expect(proximaRevision(new Date("2026-10-16T17:00:00-03:00")).texto).toBe("el lunes a las 11:30");
    expect(proximaRevision(new Date("2026-10-11T10:00:00-03:00")).texto).toBe("mañana a las 11:30");
  });
});

describe("bot de Telegram", () => {
  test("parsea comandos con o sin @bot", () => {
    expect(parsearComando("/estado")).toBe("estado");
    expect(parsearComando("/Cartera@MiBot")).toBe("cartera");
    expect(parsearComando("/start")).toBe("ayuda");
    expect(parsearComando("hola")).toBeNull();
    expect(parsearComando("/rm -rf")).toBeNull();
  });
  test("respuestas en castellano y con HTML escapado", () => {
    const e = interpretarEstado({ aportes: { paper: { total: 900000 } } });
    const txt = textoEstado({ modo: "paper", estado: e, corrida: c, ultimaRevision: null });
    expect(txt).toMatch(/Tu cartera vale <b>\$ 1\.000\.000<\/b>/);
    expect(txt).toMatch(/práctica/);
    expect(textoCartera(c)).toMatch(/S&amp;P 500/);
    expect(textoCartera(null)).toMatch(/no hice ninguna revisión/);
    expect(textoHoy([])).toMatch(/todavía no/);
    expect(AYUDA).toMatch(/\/pausar/);
  });
});
