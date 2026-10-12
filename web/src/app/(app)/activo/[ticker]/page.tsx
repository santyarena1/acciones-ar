import Link from "next/link";
import { notFound } from "next/navigation";
import { IconoAlerta, IconoAtras } from "@/components/iconos";
import { Descargo, Seccion, SinCorrida, Variacion } from "@/components/ui/piezas";
import { tenencias } from "@/lib/domain/cartera";
import { porQue } from "@/lib/domain/razones";
import { alertaLegible } from "@/lib/domain/textos";
import { contextoApp } from "@/lib/data/contexto";
import { anios, esNumero, fechaCorta, mesAnio, numero, pct, plata } from "@/lib/format";
import { CLASE_RF, SECTOR, SENAL, TIPO, VALOR_RELATIVO, nombre, tonoSenal } from "@/lib/labels";

export async function generateMetadata({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;
  return { title: nombre(decodeURIComponent(ticker).toUpperCase()) };
}

const TICKER = /^[A-Z0-9.]{1,12}$/;

export default async function Activo({ params }: { params: Promise<{ ticker: string }> }) {
  const t = decodeURIComponent((await params).ticker).toUpperCase();
  if (!TICKER.test(t)) notFound();
  const { corrida: c } = await contextoApp();
  if (!c) return <SinCorrida />;
  const r = c.porTicker.get(t) ?? null;
  const rf = c.rfPorTicker.get(t) ?? null;
  if (!r && !rf) notFound();
  const tenencia = tenencias(c).find((x) => x.ticker === t) ?? null;
  const ctxTicker = c.meta.contexto?.[t];
  const titulo = nombre(t, c.nombresRf);
  const que = rf?.clase ? CLASE_RF[rf.clase] : r?.tipo ? TIPO[r.tipo] : "Activo";
  const sector = r?.sector ? SECTOR[r.sector] : null;
  const nota = r?.score ?? rf?.score_rf ?? null;
  const tono = r ? tonoSenal(r.senal) : (rf?.score_rf ?? 0) >= 70 ? "sube" : "neutro";
  const senal = r?.senal ? SENAL[r.senal] ?? r.senal : rf ? (rf.apto_compra === false ? "No apto para comprar" : (rf.score_rf ?? 0) >= 70 ? "Buena opción" : "Neutral") : "—";

  return (
    <>
      <div className="pt-5 lg:pt-8">
        <Link href={rf ? "/bonos" : "/oportunidades"} className="inline-flex items-center gap-1.5 text-sm muted hover:text-[var(--ink)]">
          <IconoAtras width={15} height={15} /> {rf ? "Bonos y letras" : "Oportunidades"}
        </Link>
      </div>

      <header className="entra grid gap-6 pb-2 pt-5 lg:grid-cols-[1fr_auto] lg:items-end">
        <div>
          <p className="kicker">
            <span className="mono !tracking-normal">{t}</span> · {que}
            {sector ? ` · ${sector}` : ""}
          </p>
          <h1 className="titulo-pagina mt-2">{titulo}</h1>
          {tenencia ? (
            <p className="mt-3 text-sm soft">
              Tenés <b className="num">{numero(tenencia.cantidad)}</b> {tenencia.esRentaFija ? "nominales" : "unidades"} por{" "}
              <b className="num">{plata(tenencia.valor)}</b>
              {tenencia.ganancia !== null ? (
                <>
                  {" "}(<Variacion valor={tenencia.ganancia}>{pct(tenencia.ganancia, { signo: true })}</Variacion> desde la compra)
                </>
              ) : null}
              .
            </p>
          ) : null}
        </div>
        <div className="hoja flex items-center gap-5 px-5 py-4">
          <div>
            <p className="kicker">Nota del operador</p>
            <p className="display num mt-1 text-5xl leading-none">
              {esNumero(nota) ? Math.round(nota) : "—"}
              <span className="text-xl muted">/100</span>
            </p>
          </div>
          <div className="h-12 w-px" style={{ background: "var(--line)" }} />
          <div>
            <p className="kicker">Qué dice</p>
            <p className={`mt-1 text-lg font-semibold ${tono}`}>{senal}</p>
          </div>
        </div>
      </header>

      <Seccion titulo="Por qué">
        <p className="max-w-3xl text-[1.08rem] leading-relaxed">{porQue({ ranking: r, rentaFija: rf })}</p>
        {r?.alertas ? (
          <p className="mt-3 flex items-start gap-2 text-sm" style={{ color: "var(--warn)" }}>
            <IconoAlerta width={16} height={16} className="mt-0.5 flex-none" /> {alertaLegible(r.alertas)}
          </p>
        ) : null}
        {r?.nota ? <p className="mt-2 text-sm muted">{r.nota.replace("ETF / commodity: solo técnico", "Es un fondo: se analiza solo por su precio (no tiene balances).")}</p> : null}
        {rf?.apto_compra === false && rf.motivo_no_apto ? <p className="mt-2 text-sm muted">No lo compra: {rf.motivo_no_apto}.</p> : null}
      </Seccion>

      <Seccion titulo="Los números">
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-[var(--radius)] border sm:grid-cols-3 lg:grid-cols-4" style={{ background: "var(--line)" }}>
          {(r ? datosAccion(r) : rf ? datosBono(rf) : []).map(([k, v, ayuda]) => (
            <div key={k} className="p-4" style={{ background: "var(--bg-sheet)" }}>
              <dt className="text-xs muted">{k}</dt>
              <dd className="num mt-1 text-lg font-semibold">{v}</dd>
              {ayuda ? <dd className="mt-0.5 text-xs muted">{ayuda}</dd> : null}
            </div>
          ))}
        </dl>
      </Seccion>

      {ctxTicker && (ctxTicker.recomendaciones.length || ctxTicker.noticias.length) ? (
        <Seccion titulo="Qué dicen los analistas" bajada="Del reporte semanal de Gorostiaga Bursátil (últimas semanas).">
          <div className="grid gap-8 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
            <div>
              <h3 className="kicker mb-3">Recomendaciones</h3>
              {ctxTicker.recomendaciones.length ? (
                <ul className="grid gap-2">
                  {ctxTicker.recomendaciones.map((rec, i) => (
                    <li key={i} className="hoja-plana flex items-center justify-between gap-3 p-3.5">
                      <span>
                        <b>{rec.fuente ?? "Analista"}</b>
                        <span className="block text-xs muted">{fechaCorta(rec.fecha)}</span>
                      </span>
                      <span className="text-right">
                        <span className="pastilla" data-tono={/compr/i.test(rec.rating ?? "") ? "sube" : /vend/i.test(rec.rating ?? "") ? "baja" : undefined}>
                          {rec.rating ?? "—"}
                        </span>
                        {esNumero(rec.precio_objetivo_usd) ? <span className="num mt-1 block text-xs muted">Objetivo US$ {numero(rec.precio_objetivo_usd, 2)}</span> : null}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm muted">Sin recomendaciones recientes.</p>
              )}
              {esNumero(ctxTicker.upside_consenso) ? (
                <p className="mt-3 text-sm">
                  Precio objetivo promedio: <Variacion valor={ctxTicker.upside_consenso}>{pct(ctxTicker.upside_consenso, { signo: true, decimales: 0 })}</Variacion> contra hoy.
                </p>
              ) : null}
            </div>
            <div>
              <h3 className="kicker mb-3">Noticias</h3>
              <ul className="grid gap-4">
                {ctxTicker.noticias.map((n, i) => (
                  <li key={i} className="border-l-2 pl-4" style={{ borderColor: "var(--accent)" }}>
                    <p className="text-xs muted">{fechaCorta(n.fecha)}</p>
                    <p className="mt-1 leading-relaxed">{n.texto}</p>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Seccion>
      ) : null}
      <Descargo />
    </>
  );
}

type Dato = [string, React.ReactNode, string?];

function datosAccion(r: NonNullable<ReturnType<Map<string, import("@/lib/domain/schemas").FilaRanking>["get"]>>): Dato[] {
  const v = (x: number | null | undefined) => (esNumero(x) ? <Variacion valor={x}>{pct(x, { signo: true })}</Variacion> : "—");
  return [
    ["Precio", plata(r.precio_ars), esNumero(r.precio_usd) ? `US$ ${numero(r.precio_usd, 2)}` : undefined],
    ["Últimos 3 meses", v(r.mom_3m), "en dólares"],
    ["Últimos 6 meses", v(r.mom_6m), "en dólares"],
    ["Último año", v(r.mom_12m_1m), "sin el último mes"],
    ["Desde su máximo", v(r.dist_max_52s), "del último año"],
    ["Cuánto se mueve", esNumero(r.vol_anual) ? pct(r.vol_anual, { decimales: 0 }) : "—", "variación típica en un año"],
    ["Tendencia", r.sobre_sma200 === true ? "Alcista" : r.sobre_sma200 === false ? "Bajista" : "—", "vs. promedio de 10 meses"],
    ["Se opera por día", esNumero(r.vol_ars_20d) ? `$ ${numero(r.vol_ars_20d / 1e6, 0)} M` : "—", r.liquido === false ? "poco: no compra" : undefined],
  ];
}

function datosBono(f: import("@/lib/domain/schemas").FilaRentaFija): Dato[] {
  return [
    ["Rinde por año", pct(f.tir), f.clase === "cer" ? "por encima de la inflación" : f.moneda === "USD" || f.clase?.endsWith("usd") ? "en dólares" : "en pesos"],
    ["Plazo promedio", anios(f.duration), "cuánto tarda en devolverte la plata"],
    ["Vence", mesAnio(f.vencimiento), esNumero(f.dias) ? `en ${numero(f.dias)} días` : undefined],
    ["Precio", plata(f.precio_ars, { decimales: 2 }), "cada 100 nominales"],
    ["Frente a parecidos", f.senal_rv ? VALOR_RELATIVO[f.senal_rv] ?? "—" : "—", esNumero(f.spread_vs_curva_pb) ? `${numero(f.spread_vs_curva_pb)} puntos vs. la curva` : undefined],
    ["Paridad", esNumero(f.paridad) ? pct(f.paridad, { decimales: 0 }) : "—", "precio vs. valor técnico"],
    ["Emisor", f.emisor ?? (f.clase === "on_usd" ? "Empresa" : "Tesoro nacional"), f.ley ? `ley ${f.ley}` : undefined],
    ["Se opera por día", esNumero(f.volumen_ars) ? `$ ${numero(f.volumen_ars / 1e6, 0)} M` : "—"],
  ];
}
