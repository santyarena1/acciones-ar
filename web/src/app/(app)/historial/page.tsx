import Link from "next/link";
import { FilaEvento } from "@/components/eventos";
import { Descargo, Encabezado, Vacio } from "@/components/ui/piezas";
import { TIPOS_VISIBLES, type Evento } from "@/lib/domain/eventos";
import { contextoApp } from "@/lib/data/contexto";
import { eventosRecientes } from "@/lib/data/eventos";
import { diaAR, tituloDia } from "@/lib/format";

export const metadata = { title: "Historial" };

const FILTROS = {
  importante: { label: "Lo importante", tipos: TIPOS_VISIBLES.filter((t) => t !== "corrida") },
  operaciones: { label: "Compras y ventas", tipos: ["orden", "descartada", "cancelacion"] },
  plata: { label: "Plata", tipos: ["aporte", "pedido_fondos", "ajuste_aportes", "comando"] },
  todo: { label: "Todo", tipos: [...TIPOS_VISIBLES] },
} as const;
type Filtro = keyof typeof FILTROS;

export default async function Historial({ searchParams }: { searchParams: Promise<{ ver?: string }> }) {
  const { ver } = await searchParams;
  const filtro: Filtro = ver && ver in FILTROS ? (ver as Filtro) : "importante";
  const ctx = await contextoApp();
  const eventos = await eventosRecientes({ tipos: FILTROS[filtro].tipos, modo: ctx.modo, limite: 400 });
  const dias = new Map<string, Evento[]>();
  for (const e of eventos) {
    const d = diaAR(e.ts);
    dias.set(d, [...(dias.get(d) ?? []), e]);
  }
  const nombres = ctx.corrida?.nombresRf;

  return (
    <>
      <Encabezado kicker="Historial" titulo="Todo lo que hizo">
        Cada compra, venta, depósito y aviso del operador, del más nuevo al más viejo.
        {ctx.modo === "paper" ? " Estás viendo la cuenta de práctica." : " Estás viendo tu cuenta real."}
      </Encabezado>

      <div className="desliza -mx-4 mb-6 px-4 sm:mx-0 sm:px-0">
        <nav className="segmentado" aria-label="Filtrar">
          {(Object.keys(FILTROS) as Filtro[]).map((k) => (
            <Link key={k} href={k === "importante" ? "/historial" : `/historial?ver=${k}`} aria-current={k === filtro ? "true" : undefined} scroll={false}>
              {FILTROS[k].label}
            </Link>
          ))}
        </nav>
      </div>

      {eventos.length === 0 ? (
        <Vacio titulo="Todavía no hay nada acá">Cuando el operador haga su primera revisión, vas a ver acá cada paso que dé.</Vacio>
      ) : (
        <ol className="relative grid gap-8">
          {[...dias.entries()].map(([dia, evs], i) => (
            <li key={dia} className="entra grid gap-1 lg:grid-cols-[11rem_1fr] lg:gap-8" style={{ ["--i" as string]: Math.min(i, 6) }}>
              <h2 className="sticky top-[60px] z-[1] -mx-4 bg-[color-mix(in_oklab,var(--bg)_90%,transparent)] px-4 py-2 backdrop-blur lg:static lg:mx-0 lg:bg-transparent lg:p-0 lg:pt-3">
                <span className="display text-[1.5rem] first-letter:uppercase">{tituloDia(dia)}</span>
                <span className="ml-2 text-xs muted lg:ml-0 lg:block">
                  {evs.length} {evs.length === 1 ? "evento" : "eventos"}
                </span>
              </h2>
              <ul className="hoja-plana divide-y px-4" style={{ borderColor: "var(--line)" }}>
                {evs.map((e) => (
                  <FilaEvento key={e.id} evento={e} nombres={nombres} />
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
      {eventos.length >= 400 ? <p className="mt-6 text-center text-xs muted">Se muestran los últimos 400 eventos.</p> : null}
      <Descargo />
    </>
  );
}
