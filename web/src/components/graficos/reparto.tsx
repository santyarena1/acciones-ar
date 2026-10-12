import type { RepartoClase } from "@/lib/domain/cartera";
import { pct, plataCorta } from "@/lib/format";
import { CLASE, CLASE_CORTA } from "@/lib/labels";

/**
 * Reparto por clase: barra = cómo está hoy, marca vertical = lo que pide tu perfil.
 * Cada fila lleva el nombre y los dos números en texto (el color nunca es el único canal).
 */
export function BarrasReparto({ filas, total }: { filas: RepartoClase[]; total?: number | null }) {
  const max = Math.max(0.5, ...filas.flatMap((f) => [f.actual, f.objetivo])) * 1.08;
  return (
    <div className="grid gap-4">
      <div className="flex items-center gap-4 text-xs muted" aria-hidden="true">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2 w-5 rounded-full" style={{ background: "var(--ink-3)" }} /> Hoy
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-3 w-[2px]" style={{ background: "var(--ink)" }} /> Objetivo
        </span>
      </div>
      <ul className="grid gap-4">
        {filas.map((f, i) => {
          const desvio = f.actual - f.objetivo;
          return (
            <li key={f.clase} className="grid gap-1.5" style={{ ["--c" as string]: `var(--c-${f.clase})`, ["--i" as string]: i }}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="flex items-center gap-2 font-medium">
                  <span className="swatch" data-clase={f.clase} aria-hidden="true" />
                  <span className="sm:hidden">{CLASE_CORTA[f.clase]}</span>
                  <span className="hidden sm:inline">{CLASE[f.clase]}</span>
                </span>
                <span className="num whitespace-nowrap">
                  <b className="font-semibold">{pct(f.actual, { decimales: 0 })}</b>
                  <span className="muted"> / {pct(f.objetivo, { decimales: 0 })}</span>
                  {total ? <span className="muted hidden md:inline"> · {plataCorta(f.actual * total)}</span> : null}
                </span>
              </div>
              <div className="barra-pista" role="img" aria-label={`${CLASE[f.clase]}: hoy ${pct(f.actual, { decimales: 0 })}, objetivo ${pct(f.objetivo, { decimales: 0 })}`}>
                <div className="barra-relleno" data-clase={f.clase} style={{ width: `${(f.actual / max) * 100}%` }} />
                {f.objetivo > 0 ? <div className="barra-meta" style={{ left: `${(f.objetivo / max) * 100}%` }} /> : null}
              </div>
              {Math.abs(desvio) >= 0.05 ? (
                <p className="text-xs muted">
                  {desvio > 0 ? "Sobra" : "Falta"} {pct(Math.abs(desvio), { decimales: 0 })} para llegar al objetivo
                  {f.clase === "caja" && desvio > 0 ? ": el operador lo va a ir invirtiendo." : "."}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Tira apilada: la composición entera de un vistazo (con hueco de 2px entre segmentos). */
export function TiraComposicion({ partes }: { partes: { clase: string; peso: number }[] }) {
  const visibles = partes.filter((p) => p.peso > 0.002);
  return (
    <div className="flex h-3.5 w-full gap-[2px] overflow-hidden rounded-full" role="img" aria-label={visibles.map((p) => `${CLASE[p.clase] ?? p.clase} ${pct(p.peso, { decimales: 0 })}`).join(", ")}>
      {visibles.map((p, i) => (
        <span
          key={p.clase}
          className="barra-relleno !static block h-full !rounded-none first:!rounded-l-full last:!rounded-r-full"
          data-clase={p.clase}
          style={{ ["--c" as string]: `var(--c-${p.clase})`, ["--i" as string]: i, flex: `${p.peso} 1 0` }}
        />
      ))}
    </div>
  );
}
