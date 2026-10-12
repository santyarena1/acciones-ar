import Link from "next/link";
import { IconoFlecha } from "@/components/iconos";
import { TablaOportunidades } from "@/components/tabla-oportunidades";
import { Descargo, Encabezado, Seccion, SinCorrida, Vacio, Variacion } from "@/components/ui/piezas";
import { destacadas, filasOportunidades } from "@/lib/domain/oportunidades";
import { contextoApp } from "@/lib/data/contexto";
import { haceCuanto, pct } from "@/lib/format";

export const metadata = { title: "Oportunidades" };

export default async function Oportunidades() {
  const { corrida: c } = await contextoApp();
  if (!c) {
    return (
      <>
        <Encabezado kicker="Oportunidades" titulo="Lo que mira el operador" />
        <SinCorrida />
      </>
    );
  }
  const top = destacadas(c);
  const filas = filasOportunidades(c);
  return (
    <>
      <Encabezado kicker="Oportunidades" titulo="Lo que mira el operador">
        Todo lo que analiza, de mejor a peor. Revisado {haceCuanto(c.creada)}. Las acciones argentinas no se eligen por
        puntaje: el operador tiene las más líquidas en partes iguales (le ganó al puntaje en las pruebas 2018–2026).
      </Encabezado>

      <nav className="entra -mt-2 mb-2 flex gap-2" aria-label="Secciones de mercado">
        <span className="pastilla" aria-current="page">Acciones y CEDEARs</span>
        <Link className="pastilla hover:!text-[var(--ink)]" href="/bonos">
          Bonos y letras <IconoFlecha width={13} height={13} />
        </Link>
      </nav>

      <Seccion titulo="Las mejores ideas de hoy" bajada="CEDEARs con señal de compra y el porqué, en criollo.">
        {top.length ? (
          <ol className="grid gap-px overflow-hidden rounded-[var(--radius)] border md:grid-cols-2" style={{ borderColor: "var(--line)", background: "var(--line)" }}>
            {top.map((d, i) => (
              <li key={d.ticker} className="entra relative" style={{ ["--i" as string]: i + 1, background: "var(--bg-sheet)" }}>
                <Link href={`/activo/${encodeURIComponent(d.ticker)}`} className="group grid h-full grid-cols-[auto_1fr] gap-4 p-5 transition-colors hover:bg-[var(--bg-hover)] sm:p-6">
                  <span className="display num text-[2.6rem] leading-none" style={{ color: "var(--accent)" }} aria-hidden="true">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span className="min-w-0">
                    <span className="flex items-baseline justify-between gap-3">
                      <span className="text-[1.05rem] font-semibold leading-snug group-hover:underline group-hover:underline-offset-4">{d.nombre}</span>
                      <span className="num whitespace-nowrap text-sm">
                        <b>{Math.round(d.puntaje)}</b>
                        <span className="muted">/100</span>
                      </span>
                    </span>
                    <span className="mt-0.5 block text-xs muted">
                      <span className="mono">{d.ticker}</span> · {d.que}
                      {d.enCartera ? " · ya la tenés" : ""}
                    </span>
                    <span className="mt-2.5 block text-sm leading-relaxed soft">{d.frase}</span>
                    {d.mom6m !== null ? (
                      <span className="mt-2 block text-xs muted">
                        En 6 meses: <Variacion valor={d.mom6m}>{pct(d.mom6m, { signo: true })}</Variacion> en dólares
                      </span>
                    ) : null}
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        ) : (
          <Vacio titulo="Hoy no hay señales de compra claras">El operador espera: no compra por comprar.</Vacio>
        )}
      </Seccion>

      <Seccion titulo="Todo el universo" bajada="Tocá cualquier fila para ver la ficha completa.">
        <TablaOportunidades filas={filas} />
      </Seccion>
      <Descargo />
    </>
  );
}
