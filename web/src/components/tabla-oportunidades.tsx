"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { FilaOportunidad, Grupo } from "@/lib/domain/oportunidades";
import { pct, plata } from "@/lib/format";
import { IconoBuscar } from "./iconos";

type Orden = "puntaje" | "nombre" | "dato" | "precio";

const FILTROS: { v: Grupo | "todo"; label: string }[] = [
  { v: "todo", label: "Todo" },
  { v: "ar", label: "Acciones AR" },
  { v: "cedear", label: "CEDEARs" },
  { v: "rf", label: "Bonos y letras" },
];

function sinTildes(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/** Tabla completa: buscar, filtrar por tipo y ordenar. En el teléfono se ve como lista compacta. */
export function TablaOportunidades({ filas }: { filas: FilaOportunidad[] }) {
  const [q, setQ] = useState("");
  const [grupo, setGrupo] = useState<Grupo | "todo">("todo");
  const [orden, setOrden] = useState<Orden>("puntaje");
  const [asc, setAsc] = useState(false);

  const vista = useMemo(() => {
    const qq = sinTildes(q.trim());
    const f = filas.filter(
      (x) => (grupo === "todo" || x.grupo === grupo) && (!qq || sinTildes(`${x.nombre} ${x.ticker} ${x.que}`).includes(qq)),
    );
    const val = (x: FilaOportunidad): number | string | null => (orden === "nombre" ? x.nombre : x[orden]);
    return [...f].sort((a, b) => {
      const va = val(a);
      const vb = val(b);
      if (va === null) return 1;
      if (vb === null) return -1;
      const cmp = typeof va === "string" ? va.localeCompare(String(vb), "es") : va - (vb as number);
      return asc ? cmp : -cmp;
    });
  }, [filas, q, grupo, orden, asc]);

  function ordenar(o: Orden) {
    if (o === orden) setAsc(!asc);
    else {
      setOrden(o);
      setAsc(o === "nombre");
    }
  }

  const etiquetaDato = grupo === "rf" ? "Rinde por año" : grupo === "todo" ? "Suba 6 m / Rinde" : "Suba en 6 meses";

  const Th = ({ o, children, der }: { o: Orden; children: React.ReactNode; der?: boolean }) => (
    <th className={der ? "der" : undefined} aria-sort={orden === o ? (asc ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => ordenar(o)} className="inline-flex items-center gap-1 uppercase tracking-[inherit] hover:text-[var(--ink)]">
        {children}
        <span aria-hidden="true" className={orden === o ? "" : "opacity-0"}>
          {asc ? "↑" : "↓"}
        </span>
      </button>
    </th>
  );

  return (
    <div className="grid gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="desliza -mx-4 px-4 sm:mx-0 sm:px-0">
          <div className="segmentado" role="group" aria-label="Tipo de activo">
            {FILTROS.map((f) => (
              <button key={f.v} type="button" aria-pressed={grupo === f.v} onClick={() => setGrupo(f.v)}>
                {f.label}
              </button>
            ))}
          </div>
        </div>
        <label className="relative block sm:w-72">
          <span className="sr-only">Buscar</span>
          <IconoBuscar width={17} height={17} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 muted" />
          <input className="input !min-h-[42px] !pl-10" type="search" placeholder="Buscar por nombre o símbolo" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
      </div>

      <p className="text-xs muted" aria-live="polite">
        {vista.length} {vista.length === 1 ? "resultado" : "resultados"}. El puntaje va de 0 a 100: arriba de 68 el modelo la considera para comprar.
      </p>

      {/* teléfono: lista */}
      <ul className="md:hidden">
        {vista.slice(0, 120).map((x) => (
          <li key={`${x.grupo}-${x.ticker}`} className="border-b" style={{ borderColor: "var(--line)" }}>
            <Link href={`/activo/${encodeURIComponent(x.ticker)}`} className="grid grid-cols-[1fr_auto] items-center gap-3 py-3">
              <span className="min-w-0">
                <span className="block truncate font-medium">
                  {x.nombre}
                  {x.enCartera ? <span className="ml-1.5 align-middle text-[0.65rem] font-semibold uppercase tracking-wider" style={{ color: "var(--accent)" }}>tenés</span> : null}
                </span>
                <span className="block truncate text-xs muted">
                  <span className="mono">{x.ticker}</span> · {x.que}
                </span>
              </span>
              <span className="text-right">
                <Puntaje v={x.puntaje} />
                <span className={`block text-xs ${x.tono}`}>{x.senal}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>

      {/* escritorio: tabla */}
      <div className="hoja-plana desliza hidden max-h-[70vh] md:block">
        <table className="tabla">
          <thead>
            <tr>
              <Th o="nombre">Activo</Th>
              <th>Qué es</th>
              <Th o="puntaje" der>
                Puntaje
              </Th>
              <th>Qué dice</th>
              <Th o="dato" der>
                {etiquetaDato}
              </Th>
              <Th o="precio" der>
                Precio
              </Th>
            </tr>
          </thead>
          <tbody>
            {vista.map((x) => (
              <tr key={`${x.grupo}-${x.ticker}`}>
                <td>
                  <Link href={`/activo/${encodeURIComponent(x.ticker)}`} className="font-medium underline-offset-4 hover:underline">
                    {x.nombre}
                  </Link>
                  <span className="mono ml-2 muted">{x.ticker}</span>
                  {x.enCartera ? <span className="ml-2 text-[0.65rem] font-semibold uppercase tracking-wider" style={{ color: "var(--accent)" }}>tenés</span> : null}
                </td>
                <td className="soft">{x.que}</td>
                <td className="der">
                  <Puntaje v={x.puntaje} />
                </td>
                <td className={x.tono}>{x.senal}</td>
                <td className="der num">{x.grupo === "rf" ? pct(x.dato) : pct(x.dato, { signo: true })}</td>
                <td className="der num soft">{plata(x.precio)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Puntaje({ v }: { v: number | null }) {
  if (v === null) return <span className="muted">—</span>;
  const w = Math.max(0, Math.min(100, v));
  return (
    <span className="inline-flex items-center gap-2">
      <span className="hidden h-1.5 w-12 overflow-hidden rounded-full lg:block" style={{ background: "var(--bg-sunk)" }} aria-hidden="true">
        <span className="block h-full rounded-full" style={{ width: `${w}%`, background: w >= 68 ? "var(--gain)" : w < 40 ? "var(--loss)" : "var(--ink-3)" }} />
      </span>
      <span className="num font-semibold">{Math.round(v)}</span>
    </span>
  );
}
