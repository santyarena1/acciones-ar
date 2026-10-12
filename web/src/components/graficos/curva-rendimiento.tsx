"use client";

import { useMemo, useState } from "react";
import { scaleLinear, scaleTime } from "@visx/scale";
import { AreaClosed, Line, LinePath } from "@visx/shape";
import { curveMonotoneX } from "@visx/curve";
import { fechaCorta, hora, pct, plata } from "@/lib/format";
import { useAncho } from "./usar-ancho";

export interface PuntoCurva {
  ts: string;
  operador: number;
  noHacerNada: number | null;
  valor: number;
}

const ALTO = 220;
const M = { arriba: 16, derecha: 64, abajo: 26, izquierda: 8 };

/**
 * Rendimiento del operador vs. "no hacer nada", ambos en % desde el arranque (un solo eje).
 * Hover/tap: línea guía + valores del momento. Tabla accesible debajo (oculta a la vista).
 */
export function CurvaRendimiento({ puntos }: { puntos: PuntoCurva[] }) {
  const { ref, ancho } = useAncho<HTMLDivElement>();
  const [activo, setActivo] = useState<number | null>(null);

  const datos = useMemo(() => puntos.map((p) => ({ ...p, t: new Date(p.ts).getTime() })), [puntos]);
  const ancho_plot = ancho - M.izquierda - M.derecha;
  const alto_plot = ALTO - M.arriba - M.abajo;

  const x = useMemo(() => {
    const ts = datos.map((d) => d.t);
    return scaleTime({ domain: [Math.min(...ts), Math.max(...ts)], range: [0, ancho_plot] });
  }, [datos, ancho_plot]);
  const y = useMemo(() => {
    const vals = datos.flatMap((d) => [d.operador, d.noHacerNada ?? d.operador]);
    const lo = Math.min(0, ...vals);
    const hi = Math.max(0, ...vals);
    const pad = Math.max((hi - lo) * 0.15, 0.005);
    return scaleLinear({ domain: [lo - pad, hi + pad], range: [alto_plot, 0], nice: true });
  }, [datos, alto_plot]);

  const ticks = y.ticks(4);
  const ultimo = datos[datos.length - 1];
  const sel = activo !== null ? datos[activo] : ultimo;
  const conBm = datos.some((d) => d.noHacerNada !== null);
  const bm = datos.filter((d) => d.noHacerNada !== null);

  function mover(clientX: number, rect: DOMRect) {
    const px = clientX - rect.left - M.izquierda;
    const t = x.invert(px).getTime();
    let mejor = 0;
    for (let i = 1; i < datos.length; i++) {
      if (Math.abs(datos[i]!.t - t) < Math.abs(datos[mejor]!.t - t)) mejor = i;
    }
    setActivo(mejor);
  }

  if (!ultimo || !sel) return null;
  const largo = Math.ceil(ancho_plot * 2.2);

  return (
    <figure className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-3">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[0.8rem]" aria-hidden="true">
        <span className="inline-flex items-center gap-2">
          <span className="h-[3px] w-5 rounded-full" style={{ background: "var(--serie-operador)" }} />
          <span className="soft">Tu operador</span>
          <b className="num font-semibold">{pct(sel.operador, { signo: true })}</b>
        </span>
        {conBm ? (
          <span className="inline-flex items-center gap-2">
            <span className="h-0 w-5 border-t-2 border-dashed" style={{ borderColor: "var(--serie-bm)" }} />
            <span className="soft">No hacer nada</span>
            <b className="num font-semibold">{pct(sel.noHacerNada, { signo: true })}</b>
          </span>
        ) : null}
        <span className="muted num basis-full text-xs sm:ml-auto sm:basis-auto">
          {fechaCorta(sel.ts)} {hora(sel.ts)} · {plata(sel.valor)}
        </span>
      </div>
      <div ref={ref} className="relative min-w-0 touch-pan-y select-none [&>svg]:block [&>svg]:max-w-full">
        <svg
          width={ancho}
          height={ALTO}
          role="img"
          aria-label={`Rendimiento del operador ${pct(ultimo.operador, { signo: true })}${conBm ? ` contra ${pct(ultimo.noHacerNada, { signo: true })} de no hacer nada` : ""}`}
          onPointerMove={(e) => mover(e.clientX, e.currentTarget.getBoundingClientRect())}
          onPointerDown={(e) => mover(e.clientX, e.currentTarget.getBoundingClientRect())}
          onPointerLeave={() => setActivo(null)}
        >
          <defs>
            <linearGradient id="lavado-op" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--serie-operador)" stopOpacity={0.18} />
              <stop offset="100%" stopColor="var(--serie-operador)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <g transform={`translate(${M.izquierda},${M.arriba})`}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={0} x2={ancho_plot} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth={t === 0 ? 1.2 : 1} />
                <text x={ancho_plot + 10} y={y(t)} dy="0.32em" fontSize={11} fill="var(--ink-3)" className="num">
                  {pct(t, { signo: true, decimales: Math.abs(y.domain()[1]! - y.domain()[0]!) < 0.05 ? 1 : 0 })}
                </text>
              </g>
            ))}
            <AreaClosed
              data={datos}
              x={(d) => x(d.t)}
              y={(d) => y(d.operador)}
              yScale={y}
              curve={curveMonotoneX}
              fill="url(#lavado-op)"
            />
            {bm.length > 1 ? (
              <LinePath
                data={bm}
                x={(d) => x(d.t)}
                y={(d) => y(d.noHacerNada ?? 0)}
                curve={curveMonotoneX}
                stroke="var(--serie-bm)"
                strokeWidth={2}
                strokeDasharray="5 5"
                strokeLinecap="round"
              />
            ) : null}
            <LinePath
              data={datos}
              x={(d) => x(d.t)}
              y={(d) => y(d.operador)}
              curve={curveMonotoneX}
              stroke="var(--serie-operador)"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              className="traza"
              style={{ ["--largo" as string]: largo }}
            />
            <text x={0} y={alto_plot + 18} fontSize={11} fill="var(--ink-3)">
              {fechaCorta(datos[0]!.ts)}
            </text>
            <text x={ancho_plot} y={alto_plot + 18} fontSize={11} fill="var(--ink-3)" textAnchor="end">
              {fechaCorta(ultimo.ts)}
            </text>
            {activo !== null ? (
              <Line from={{ x: x(sel.t), y: 0 }} to={{ x: x(sel.t), y: alto_plot }} stroke="var(--ink-3)" strokeWidth={1} />
            ) : null}
            {sel.noHacerNada !== null ? (
              <circle cx={x(sel.t)} cy={y(sel.noHacerNada)} r={4} fill="var(--serie-bm)" stroke="var(--bg-sheet)" strokeWidth={2} />
            ) : null}
            <circle cx={x(sel.t)} cy={y(sel.operador)} r={5} fill="var(--serie-operador)" stroke="var(--bg-sheet)" strokeWidth={2} />
          </g>
        </svg>
      </div>
      <figcaption className="sr-only">
        <table>
          <caption>Rendimiento por revisión</caption>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Tu operador</th>
              <th>No hacer nada</th>
              <th>Valor</th>
            </tr>
          </thead>
          <tbody>
            {datos.slice(-30).map((d) => (
              <tr key={d.ts}>
                <td>{fechaCorta(d.ts)}</td>
                <td>{pct(d.operador, { signo: true })}</td>
                <td>{pct(d.noHacerNada, { signo: true })}</td>
                <td>{plata(d.valor)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </figcaption>
    </figure>
  );
}
