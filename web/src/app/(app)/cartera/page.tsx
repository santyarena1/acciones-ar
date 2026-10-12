import Link from "next/link";
import { TiraComposicion } from "@/components/graficos/reparto";
import { IconoAlerta } from "@/components/iconos";
import { Descargo, Encabezado, SinCorrida, Variacion, Vacio } from "@/components/ui/piezas";
import { tenencias, type Tenencia } from "@/lib/domain/cartera";
import { alertaLegible } from "@/lib/domain/textos";
import { contextoApp } from "@/lib/data/contexto";
import { haceCuanto, numero, pct, plata } from "@/lib/format";
import { CLASE, ORDEN_CLASES, SENAL, type ClaseCartera } from "@/lib/labels";

export const metadata = { title: "Mi cartera" };

export default async function Cartera() {
  const { corrida: c } = await contextoApp();
  if (!c) {
    return (
      <>
        <Encabezado kicker="Mi cartera" titulo="Lo que tenés" />
        <SinCorrida />
      </>
    );
  }
  const items = tenencias(c);
  const total = c.meta.cartera.valor_total ?? 0;
  const caja = c.meta.cartera.caja ?? 0;
  const grupos = ORDEN_CLASES.filter((k) => k !== "caja")
    .map((clase) => ({ clase, items: items.filter((t) => t.clase === clase) }))
    .filter((g) => g.items.length);
  const partes = [
    ...grupos.map((g) => ({ clase: g.clase as string, peso: g.items.reduce((a, t) => a + t.peso, 0) })),
    { clase: "caja", peso: total ? caja / total : 0 },
  ];

  return (
    <>
      <Encabezado kicker="Mi cartera" titulo="Lo que tenés">
        Cada cosa que compró el operador, cuánto vale hoy y por qué la tiene. Datos de la revisión de {haceCuanto(c.creada)}.
      </Encabezado>

      <section className="hoja entra grid gap-5 p-5 sm:p-6" style={{ ["--i" as string]: 1 }} aria-label="Composición">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="kicker">Valor total</p>
            <p className="display num mt-1 text-[2.6rem] leading-none sm:text-5xl">{plata(total)}</p>
          </div>
          <dl className="flex gap-8 text-sm">
            <div>
              <dt className="muted">Inversiones</dt>
              <dd className="num mt-0.5 font-semibold">{items.length}</dd>
            </div>
            <div>
              <dt className="muted">Efectivo</dt>
              <dd className="num mt-0.5 font-semibold">{plata(caja)}</dd>
            </div>
          </dl>
        </div>
        <TiraComposicion partes={partes} />
        <ul className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
          {partes.filter((p) => p.peso > 0.002).map((p) => (
            <li key={p.clase} className="flex items-center gap-2" style={{ ["--c" as string]: `var(--c-${p.clase})` }}>
              <span className="swatch" data-clase={p.clase} aria-hidden="true" />
              <span className="soft">{CLASE[p.clase]}</span>
              <span className="num font-semibold">{pct(p.peso, { decimales: 0 })}</span>
            </li>
          ))}
        </ul>
      </section>

      {items.length === 0 ? (
        <div className="mt-8">
          <Vacio titulo="Todavía no hay inversiones">Por ahora todo está en efectivo ({plata(caja)}). El operador va a ir comprando en las próximas revisiones.</Vacio>
        </div>
      ) : (
        grupos.map((g, gi) => <Grupo key={g.clase} clase={g.clase} items={g.items} indice={gi} />)
      )}

      <p className="mt-8 text-xs muted">
        Los bonos y letras se cuentan en “nominales” y su precio está expresado cada 100 nominales, como en IOL. La ganancia
        compara el precio de hoy contra el precio promedio al que se compró (sin comisiones).
      </p>
      <Descargo />
    </>
  );
}

function Grupo({ clase, items, indice }: { clase: ClaseCartera; items: Tenencia[]; indice: number }) {
  const subtotal = items.reduce((a, t) => a + t.valor, 0);
  const peso = items.reduce((a, t) => a + t.peso, 0);
  return (
    <section className="seccion entra" style={{ ["--i" as string]: indice + 2, ["--c" as string]: `var(--c-${clase})` }} aria-labelledby={`g-${clase}`}>
      <div className="flex items-baseline justify-between gap-3 border-b pb-2.5" style={{ borderColor: "var(--line-strong)" }}>
        <h2 id={`g-${clase}`} className="flex items-center gap-2.5">
          <span className="swatch !h-3 !w-3" data-clase={clase} aria-hidden="true" />
          <span className="titulo-seccion !text-[1.45rem]">{CLASE[clase]}</span>
        </h2>
        <p className="num text-sm">
          <b className="font-semibold">{plata(subtotal)}</b> <span className="muted">· {pct(peso, { decimales: 0 })}</span>
        </p>
      </div>
      <ul>
        {items.map((t) => (
          <FilaTenencia key={t.ticker} t={t} />
        ))}
      </ul>
    </section>
  );
}

function FilaTenencia({ t }: { t: Tenencia }) {
  return (
    <li className="group grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 border-b py-4 md:grid-cols-[minmax(0,1.3fr)_7.5rem_6rem_minmax(0,1.6fr)] md:items-start" style={{ borderColor: "var(--line)" }}>
      <div className="min-w-0">
        <Link href={`/activo/${encodeURIComponent(t.ticker)}`} className="font-semibold leading-snug underline-offset-4 group-hover:underline">
          {t.nombre}
        </Link>
        <p className="mt-0.5 text-xs muted">
          <span className="mono">{t.ticker}</span> · {t.que} · <span className="num">{numero(t.cantidad)}</span> {t.esRentaFija ? "nominales" : t.cantidad === 1 ? "unidad" : "unidades"}
        </p>
      </div>
      <div className="text-right md:order-none">
        <p className="num font-semibold">{plata(t.valor)}</p>
        <p className="num text-xs muted md:hidden">
          {pct(t.peso)} ·{" "}
          {t.ganancia !== null ? <Variacion valor={t.ganancia}>{pct(t.ganancia, { signo: true })}</Variacion> : "—"}
        </p>
        <div className="mt-1.5 hidden h-1 rounded-full md:block" style={{ background: "var(--bg-sunk)" }} aria-hidden="true">
          <div className="h-1 rounded-full" style={{ width: `${Math.min(100, t.peso * 400)}%`, background: "var(--c)" }} />
        </div>
        <p className="num mt-1 hidden text-xs muted md:block">{pct(t.peso)} de la cartera</p>
      </div>
      <div className="hidden text-right md:block">
        {t.ganancia !== null ? (
          <Variacion valor={t.ganancia} className="font-semibold">
            {pct(t.ganancia, { signo: true })}
          </Variacion>
        ) : (
          <span className="muted">—</span>
        )}
        <p className="text-xs muted">desde la compra</p>
      </div>
      <div className="col-span-2 text-sm leading-relaxed soft md:col-span-1">
        {t.senal && !t.esRentaFija ? <span className="mr-1.5 font-semibold" style={{ color: "var(--ink)" }}>{SENAL[t.senal] ?? t.senal}.</span> : null}
        {t.porque}
        {t.alerta ? (
          <p className="mt-1.5 flex items-start gap-1.5 text-[0.82rem]" style={{ color: "var(--warn)" }}>
            <IconoAlerta width={14} height={14} className="mt-0.5 flex-none" />
            <span>{alertaLegible(t.alerta)}</span>
          </p>
        ) : null}
      </div>
    </li>
  );
}
