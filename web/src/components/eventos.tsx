import { describirEvento, type Evento, type TonoEvento } from "@/lib/domain/eventos";
import { hora, plata } from "@/lib/format";

const MARCA: Record<TonoEvento, { color: string; letra: string; nombre: string }> = {
  compra: { color: "var(--gain)", letra: "C", nombre: "Compra" },
  venta: { color: "var(--accent)", letra: "V", nombre: "Venta" },
  plata: { color: "var(--c-cedears)", letra: "$", nombre: "Plata" },
  alerta: { color: "var(--warn)", letra: "!", nombre: "Aviso" },
  error: { color: "var(--loss)", letra: "×", nombre: "Problema" },
  info: { color: "var(--ink-2)", letra: "i", nombre: "Info" },
  tenue: { color: "var(--ink-3)", letra: "·", nombre: "Revisión" },
};

/** Una línea de la bitácora: hora, sello del tipo, qué pasó y (si hubo plata) el monto. */
export function FilaEvento({ evento, nombres, conFecha }: { evento: Evento; nombres?: Record<string, string>; conFecha?: string }) {
  const e = describirEvento(evento, nombres);
  const m = MARCA[e.tono];
  return (
    <li className="grid grid-cols-[2.6rem_1.75rem_1fr_auto] items-start gap-x-3 py-3" data-tono={e.tono}>
      <span className="num pt-0.5 text-xs muted">{conFecha ?? hora(evento.ts)}</span>
      <span
        className="mono grid h-7 w-7 place-items-center rounded-full text-[0.78rem] font-semibold"
        style={{ color: m.color, background: `color-mix(in oklab, ${m.color} 13%, transparent)`, boxShadow: `inset 0 0 0 1px color-mix(in oklab, ${m.color} 30%, transparent)` }}
        title={m.nombre}
        aria-hidden="true"
      >
        {m.letra}
      </span>
      <div className={`min-w-0 ${e.tono === "tenue" ? "muted" : ""}`}>
        <p className="font-medium leading-snug">
          <span className="sr-only">{m.nombre}: </span>
          {e.titulo}
        </p>
        {e.detalle ? <p className="mt-0.5 text-sm leading-snug muted">{e.detalle}</p> : null}
      </div>
      {e.monto != null && e.monto !== 0 ? (
        <span className={`num pt-0.5 text-sm font-semibold ${e.tono === "compra" ? "soft" : e.monto > 0 ? "sube" : "soft"}`}>
          {plata(e.monto, { signo: true })}
        </span>
      ) : (
        <span />
      )}
    </li>
  );
}
