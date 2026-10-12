"use client";

import { useMemo, useState } from "react";
import { scaleLinear } from "@visx/scale";
import { anios, pct } from "@/lib/format";
import { useAncho } from "./usar-ancho";

export interface PuntoBono {
  ticker: string;
  nombre: string;
  clase: string;
  tir: number;
  duracion: number;
  valor: "barato" | "caro" | "en_curva" | null;
}

export interface PanelBonos {
  id: string;
  titulo: string;
  nota: string;
  clases: { id: string; nombre: string; color: string }[];
  puntos: PuntoBono[];
}

const ALTO = 280;
const M = { arriba: 14, derecha: 16, abajo: 34, izquierda: 48 };

/**
 * Rendimiento vs. plazo (TIR vs. duration). Un panel por moneda: mezclar TIR en dólares, en pesos y por encima
 * de la inflación en un mismo eje engañaría. Hover/tap en cada punto; los baratos llevan anillo.
 */
export function CurvaBonos({ paneles }: { paneles: PanelBonos[] }) {
  const [sel, setSel] = useState(paneles[0]?.id ?? "");
  const [activo, setActivo] = useState<string | null>(null);
  const { ref, ancho } = useAncho<HTMLDivElement>();
  const panel = paneles.find((p) => p.id === sel) ?? paneles[0];
  const w = ancho - M.izquierda - M.derecha;
  const h = ALTO - M.arriba - M.abajo;

  const { x, y } = useMemo(() => {
    const pts = panel?.puntos ?? [];
    const dmax = Math.max(1, ...pts.map((p) => p.duracion));
    const tmin = Math.min(...pts.map((p) => p.tir), 0);
    const tmax = Math.max(...pts.map((p) => p.tir), 0.05);
    return {
      x: scaleLinear({ domain: [0, dmax * 1.08], range: [0, w], nice: true }),
      y: scaleLinear({ domain: [tmin < 0 ? tmin * 1.1 : 0, tmax * 1.12], range: [h, 0], nice: true }),
    };
  }, [panel, w, h]);

  if (!panel) return null;
  const color = new Map(panel.clases.map((c) => [c.id, c.color]));
  const p = panel.puntos.find((q) => q.ticker === activo) ?? null;

  return (
    <figure className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="segmentado" role="radiogroup" aria-label="Moneda">
          {paneles.map((pn) => (
            <button key={pn.id} type="button" role="radio" aria-checked={pn.id === sel} onClick={() => { setSel(pn.id); setActivo(null); }}>
              {pn.titulo}
            </button>
          ))}
        </div>
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs soft">
          {panel.clases.map((c) => (
            <li key={c.id} className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: c.color }} aria-hidden="true" />
              {c.nombre}
            </li>
          ))}
          <li className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full border-2" style={{ borderColor: "var(--gain)" }} aria-hidden="true" />
            Barato vs. sus parecidos
          </li>
        </ul>
      </div>
      <p className="text-xs muted">{panel.nota}</p>
      <div ref={ref} className="relative min-w-0 [&>svg]:block [&>svg]:max-w-full">
        <svg width={ancho} height={ALTO} role="img" aria-label={`Rendimiento según plazo: ${panel.titulo}`}>
          <g transform={`translate(${M.izquierda},${M.arriba})`}>
            {y.ticks(5).map((t) => (
              <g key={`y${t}`}>
                <line x1={0} x2={w} y1={y(t)} y2={y(t)} stroke="var(--line)" />
                <text x={-10} y={y(t)} dy="0.32em" textAnchor="end" fontSize={11} fill="var(--ink-3)" className="num">
                  {pct(t, { decimales: 0 })}
                </text>
              </g>
            ))}
            {x.ticks(6).map((t) => (
              <text key={`x${t}`} x={x(t)} y={h + 18} textAnchor="middle" fontSize={11} fill="var(--ink-3)" className="num">
                {t === 0 ? "0" : `${String(t).replace(".", ",")} a`}
              </text>
            ))}
            <text x={w} y={h + 31} textAnchor="end" fontSize={10.5} fill="var(--ink-3)">
              plazo promedio de los pagos (años) →
            </text>
            {panel.puntos.map((q) => {
              const on = q.ticker === activo;
              return (
                <g
                  key={q.ticker}
                  tabIndex={0}
                  role="button"
                  aria-label={`${q.nombre}: rinde ${pct(q.tir)} por año, plazo ${anios(q.duracion)}`}
                  onPointerEnter={() => setActivo(q.ticker)}
                  onFocus={() => setActivo(q.ticker)}
                  onClick={() => setActivo(q.ticker)}
                  style={{ cursor: "pointer", outline: "none" }}
                >
                  <circle cx={x(q.duracion)} cy={y(q.tir)} r={14} fill="transparent" />
                  {q.valor === "barato" ? <circle cx={x(q.duracion)} cy={y(q.tir)} r={on ? 10 : 8.5} fill="none" stroke="var(--gain)" strokeWidth={2} /> : null}
                  <circle cx={x(q.duracion)} cy={y(q.tir)} r={on ? 6.5 : 5} fill={color.get(q.clase) ?? "var(--ink-3)"} stroke="var(--bg-sheet)" strokeWidth={2} />
                </g>
              );
            })}
          </g>
        </svg>
        {p ? (
          <div
            className="hoja pointer-events-none absolute z-10 w-56 p-3 text-sm"
            style={{
              left: Math.min(Math.max(M.izquierda + x(p.duracion) - 112, 0), ancho - 224),
              top: Math.max(M.arriba + y(p.tir) - 104, 0),
            }}
            role="status"
          >
            <p className="font-semibold leading-snug">{p.nombre}</p>
            <p className="mono text-xs muted">{p.ticker}</p>
            <p className="num mt-1.5">
              Rinde <b>{pct(p.tir)}</b> por año
            </p>
            <p className="num text-xs muted">Plazo promedio: {anios(p.duracion)}</p>
          </div>
        ) : null}
      </div>
    </figure>
  );
}
