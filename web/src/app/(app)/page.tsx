import Link from "next/link";
import { FilaEvento } from "@/components/eventos";
import { CurvaRendimiento } from "@/components/graficos/curva-rendimiento";
import { BarrasReparto } from "@/components/graficos/reparto";
import { IconoFlecha } from "@/components/iconos";
import { Aviso, Descargo, SinCorrida, Variacion } from "@/components/ui/piezas";
import { reparto } from "@/lib/domain/cartera";
import { rendimiento } from "@/lib/domain/estado";
import { TIPOS_MOVIMIENTO } from "@/lib/domain/eventos";
import { esSoloInformativo, fechasCortas, humanizar, textoPedidoFondos } from "@/lib/domain/textos";
import { contextoApp } from "@/lib/data/contexto";
import { eventosRecientes, fotos } from "@/lib/data/eventos";
import { fechaCorta, fechaLarga, haceCuanto, pct, plata, pp } from "@/lib/format";
import { nombre, ORDEN_CLASES, REGIMEN } from "@/lib/labels";
import { nombrePerfil } from "@/lib/perfiles";

export const metadata = { title: "Inicio" };

export default async function Inicio() {
  const ctx = await contextoApp();
  const { corrida: c, estado, modo } = ctx;
  const [serie, movimientos] = await Promise.all([
    fotos(modo),
    eventosRecientes({ tipos: TIPOS_MOVIMIENTO, modo, limite: 6 }),
  ]);

  const avisos = (
    <div className="grid gap-2.5 pt-5 lg:pt-8">
      {estado.pausado ? (
        <Aviso tono="alerta" titulo="El operador está en pausa">
          No compra ni vende hasta que lo reanudes desde <Link className="underline underline-offset-4" href="/configuracion#pausa">Configuración</Link>.
        </Aviso>
      ) : null}
      {estado.pedidoFondos ? (
        <Aviso tono="alerta" titulo="El operador te pide más plata">
          {textoPedidoFondos(estado.pedidoFondos.monto, estado.pedidoFondos.recompras)}
        </Aviso>
      ) : null}
      {estado.seguimiento[modo]?.alertado ? (
        <Aviso tono="peligro" titulo="La cartera tuvo una caída fuerte">
          Cae más de 15% desde su máximo (sin contar tus depósitos). El operador no vende por esto: sigue su análisis.
        </Aviso>
      ) : null}
      {modo === "paper" ? (
        <Aviso titulo="Modo práctica">
          El operador usa plata de mentira para mostrarte cómo trabajaría. Cuando te sientas cómodo, activá el modo real en{" "}
          <Link className="underline underline-offset-4" href="/configuracion#modo">Configuración</Link>.
        </Aviso>
      ) : null}
    </div>
  );

  if (!c) {
    return (
      <>
        {avisos}
        <SinCorrida />
      </>
    );
  }

  const valor = c.meta.cartera.valor_total;
  const r = rendimiento(estado, modo, valor);
  const filasReparto = reparto(c, ORDEN_CLASES);
  const puntos = serie.map((f) => ({ ts: f.ts, operador: f.indice - 1, noHacerNada: f.bmIndice === null ? null : f.bmIndice - 1, valor: f.valor }));
  const macro = c.meta.macro;
  const tactico = c.meta.tactico;
  const reporte = c.meta.reporte_semanal;

  return (
    <>
      {avisos}

      {/* ----------------------------------------------------------- héroe */}
      <section className="mt-7 grid gap-8 lg:mt-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:gap-12" aria-label="Resumen">
        <div className="entra">
          <p className="kicker">
            {fechaLarga(new Date())} · {modo === "live" ? "Cuenta real" : "Práctica"}
          </p>
          <p className="mt-4 text-sm soft">Tu cartera vale</p>
          <p className="display num mt-1 text-[clamp(3rem,2rem+6vw,5.4rem)]" style={{ lineHeight: 0.95 }}>
            {plata(valor)}
          </p>
          {r.ganancia !== null ? (
            <p className="mt-4 text-[1.05rem]">
              <Variacion valor={r.ganancia} className="font-semibold">
                {plata(r.ganancia, { signo: true })} ({pct(r.gananciaPct, { signo: true })})
              </Variacion>{" "}
              <span className="soft">sobre lo que pusiste</span>
            </p>
          ) : null}
          <p className="mt-2 text-xs muted">
            Datos de la revisión del {fechaCorta(c.creada)} ({haceCuanto(c.creada)}). Perfil {nombrePerfil(c.meta.perfil ?? ctx.perfil).toLowerCase()}.
          </p>
        </div>

        <div className="hoja entra p-4 sm:p-5" style={{ ["--i" as string]: 2 }}>
          <div className="mb-3 flex items-baseline justify-between gap-2">
            <h2 className="font-semibold">¿Le gana a no hacer nada?</h2>
            {r.diferencia !== null ? (
              <span className="pastilla" data-tono={r.diferencia >= 0 ? "sube" : "baja"}>
                {pp(r.diferencia)}
              </span>
            ) : null}
          </div>
          {puntos.length >= 2 ? (
            <CurvaRendimiento puntos={puntos} />
          ) : (
            <div className="grid h-[220px] place-items-center rounded-xl text-center" style={{ background: "var(--bg-sunk)" }}>
              <p className="max-w-xs px-4 text-sm muted">
                La curva aparece después de la segunda revisión. Compara tu cartera contra haber comprado mitad S&amp;P 500 y mitad Merval el primer día.
              </p>
            </div>
          )}
        </div>
      </section>

      {/* ----------------------------------------------------------- libro mayor */}
      <dl className="mt-8 grid grid-cols-2 border-y lg:grid-cols-4" style={{ borderColor: "var(--line)" }}>
        {[
          { t: "Lo que pusiste", v: plata(r.aportado), sub: modo === "live" ? "Depósitos en IOL" : "En la práctica" },
          {
            t: "Ganancia real",
            v: r.ganancia !== null ? <Variacion valor={r.ganancia}>{plata(r.ganancia, { signo: true })}</Variacion> : "—",
            sub: r.gananciaPct !== null ? pct(r.gananciaPct, { signo: true }) : "Sin aportes registrados",
          },
          {
            t: "Contra no hacer nada",
            v: r.diferencia !== null ? <Variacion valor={r.diferencia}>{pp(r.diferencia)}</Variacion> : "—",
            sub: r.operador !== null ? `Vos ${pct(r.operador, { signo: true })} · Índices ${pct(r.noHacerNada, { signo: true })}` : "Se mide desde la primera revisión",
          },
          { t: "Efectivo", v: plata(c.meta.cartera.caja), sub: valor ? `${pct((c.meta.cartera.caja ?? 0) / valor, { decimales: 0 })} de la cartera` : "" },
        ].map((x, i) => (
          <div
            key={x.t}
            className="entra px-1 py-4 sm:px-4 [&:nth-child(odd)]:pr-3 [&:nth-child(even)]:border-l [&:nth-child(even)]:pl-4 lg:[&:not(:first-child)]:border-l lg:[&:not(:first-child)]:pl-5"
            style={{ borderColor: "var(--line)", ["--i" as string]: i + 3 }}
          >
            <dt className="kicker">{x.t}</dt>
            <dd className="num mt-2 text-[1.25rem] font-semibold tracking-tight sm:text-[1.4rem]">{x.v}</dd>
            <dd className="mt-0.5 text-xs muted">{x.sub}</dd>
          </div>
        ))}
      </dl>

      {/* ----------------------------------------------------------- reparto + movimientos */}
      <div className="mt-10 grid gap-10 lg:mt-14 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-14">
        <section aria-labelledby="reparto-t">
          <div className="mb-5 flex items-end justify-between">
            <div>
              <h2 id="reparto-t" className="titulo-seccion">Cómo está repartida</h2>
              <p className="mt-1 text-sm muted">Hoy contra lo que pide tu perfil.</p>
            </div>
            <Link href="/cartera" className="btn btn-chico">
              Ver cartera <IconoFlecha width={15} height={15} />
            </Link>
          </div>
          <BarrasReparto filas={filasReparto} total={valor} />
        </section>

        <section aria-labelledby="movs-t">
          <div className="mb-2 flex items-end justify-between">
            <h2 id="movs-t" className="titulo-seccion">Últimos movimientos</h2>
            <Link href="/historial" className="text-sm font-medium soft underline-offset-4 hover:underline">
              Todo el historial
            </Link>
          </div>
          {movimientos.length ? (
            <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
              {movimientos.map((e) => (
                <FilaEvento key={e.id} evento={e} nombres={c.nombresRf} conFecha={fechaCorta(e.ts)} />
              ))}
            </ul>
          ) : (
            <p className="py-6 text-sm muted">Todavía no compró ni vendió nada.</p>
          )}
        </section>
      </div>

      {/* ----------------------------------------------------------- qué está pensando */}
      <section className="seccion" aria-labelledby="piensa-t">
        <div className="mb-6 flex items-end justify-between border-b pb-3" style={{ borderColor: "var(--line)" }}>
          <h2 id="piensa-t" className="titulo-seccion">Qué está pensando</h2>
          <span className="pastilla">Argentina: {REGIMEN[macro.regimen] ?? macro.regimen}</span>
        </div>
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-14">
          {reporte?.resumen ? (
            <blockquote className="relative lg:order-2">
              <span aria-hidden="true" className="display absolute -left-1 -top-6 text-7xl leading-none" style={{ color: "var(--accent)", opacity: 0.5 }}>
                “
              </span>
              <p className="display text-[1.35rem] leading-[1.35] sm:text-[1.55rem]">{recortar(reporte.resumen, 420)}</p>
              <footer className="mt-3 text-xs muted">
                Reporte semanal de Gorostiaga Bursátil n.º {reporte.numero}, {fechaCorta(reporte.fecha)}
              </footer>
            </blockquote>
          ) : null}
          <div className="grid gap-6">
            <div>
              <h3 className="kicker mb-2">La Argentina</h3>
              <ul className="grid gap-1.5 text-[0.95rem]">
                {macro.motivos.map((m) => (
                  <li key={m} className="flex gap-2">
                    <span aria-hidden="true" className="mt-2 h-1 w-1 flex-none rounded-full" style={{ background: "var(--accent)" }} />
                    {humanizar(m)}
                  </li>
                ))}
              </ul>
            </div>
            {tactico?.motivos.length ? (
              <div>
                <h3 className="kicker mb-2">El mundo</h3>
                <ul className="grid gap-2 text-[0.95rem]">
                  {tactico.motivos.map((m) => (
                    <li key={m} className="flex gap-2">
                      <span aria-hidden="true" className="mt-2 h-1 w-1 flex-none rounded-full" style={{ background: "var(--accent)" }} />
                      <span>
                        {fechasCortas(humanizar(m))}
                        {esSoloInformativo(m) ? <span className="ml-1.5 align-middle text-[0.7rem] font-semibold uppercase tracking-wider muted">solo aviso</span> : null}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {c.ordenes.length ? (
              <div>
                <h3 className="kicker mb-2">Lo próximo del plan</h3>
                <ul className="grid gap-1.5 text-[0.95rem]">
                  {c.ordenes.slice(0, 5).map((o, i) => (
                    <li key={`${o.ticker}-${i}`} className="flex items-baseline justify-between gap-3">
                      <span>
                        {o.lado === "VENDER" ? "Vender" : "Comprar"} {nombre(o.ticker ?? "", c.nombresRf)}
                      </span>
                      <span className="num whitespace-nowrap muted">{plata(o.monto_ars)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </div>
      </section>
      <Descargo />
    </>
  );
}

function recortar(s: string, max: number): string {
  if (s.length <= max) return s;
  const corte = s.lastIndexOf(".", max);
  return corte > max * 0.5 ? s.slice(0, corte + 1) : `${s.slice(0, max).trimEnd()}…`;
}
