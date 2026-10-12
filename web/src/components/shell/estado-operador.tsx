import { haceCuanto, hora } from "@/lib/format";
import type { ContextoApp } from "@/lib/data/contexto";

/** Estado del operador en una línea: activo/pausado, práctica/real, última revisión. */
export function PastillasEstado({ ctx, compacto = false }: { ctx: ContextoApp; compacto?: boolean }) {
  const real = ctx.modo === "live";
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="pastilla" data-tono={ctx.estado.pausado ? "pausado" : "activo"}>
        <span className="punto" aria-hidden="true" />
        {ctx.estado.pausado ? "Pausado" : "Activo"}
      </span>
      <span className="pastilla" data-tono={real ? "real" : "practica"} title={real ? "Opera con tu cuenta real de IOL" : "Opera con plata de mentira"}>
        {real ? "Real" : "Práctica"}
      </span>
      {!compacto && ctx.ultimaRevision ? (
        <span className="pastilla" title={`Última revisión: ${hora(ctx.ultimaRevision)}`}>
          Revisó {haceCuanto(ctx.ultimaRevision)}
        </span>
      ) : null}
    </div>
  );
}

export function BloqueEstado({ ctx }: { ctx: ContextoApp }) {
  return (
    <div className="hoja-plana grid gap-3 p-3.5">
      <div className="kicker">El operador</div>
      <PastillasEstado ctx={ctx} compacto />
      <p className="text-xs leading-relaxed muted">
        {ctx.ultimaRevision ? (
          <>
            Última revisión {haceCuanto(ctx.ultimaRevision)}
            <span className="num"> ({hora(ctx.ultimaRevision)})</span>.
          </>
        ) : (
          "Todavía no hizo ninguna revisión."
        )}{" "}
        Revisa cada hora con el mercado abierto.
      </p>
    </div>
  );
}
