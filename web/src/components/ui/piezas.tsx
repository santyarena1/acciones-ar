import Link from "next/link";
import type { ReactNode } from "react";
import { proximaRevision } from "@/lib/domain/horario";
import { tono as tonoDe } from "@/lib/format";
import { IconoAlerta, IconoInfo } from "../iconos";

export function Encabezado({ kicker, titulo, children }: { kicker: string; titulo: ReactNode; children?: ReactNode }) {
  return (
    <header className="encabezado entra">
      <p className="kicker">{kicker}</p>
      <h1 className="titulo-pagina mt-2">{titulo}</h1>
      {children ? <div className="mt-3 max-w-2xl soft">{children}</div> : null}
    </header>
  );
}

export function Seccion({
  titulo,
  bajada,
  accion,
  children,
  id,
  className = "",
}: {
  titulo: ReactNode;
  bajada?: ReactNode;
  accion?: ReactNode;
  children: ReactNode;
  id?: string;
  className?: string;
}) {
  return (
    <section className={`seccion ${className}`} aria-labelledby={id ? `${id}-t` : undefined} id={id}>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3 border-b pb-3" style={{ borderColor: "var(--line)" }}>
        <div>
          <h2 id={id ? `${id}-t` : undefined} className="titulo-seccion">
            {titulo}
          </h2>
          {bajada ? <p className="mt-1 text-sm muted">{bajada}</p> : null}
        </div>
        {accion}
      </div>
      {children}
    </section>
  );
}

export function Aviso({
  tono,
  titulo,
  children,
}: {
  tono?: "alerta" | "peligro" | "ok" | "info";
  titulo: ReactNode;
  children?: ReactNode;
}) {
  const Icono = tono === "alerta" || tono === "peligro" ? IconoAlerta : IconoInfo;
  return (
    <div className="aviso" data-tono={tono ?? "info"} role={tono === "peligro" ? "alert" : undefined}>
      <Icono />
      <div className="min-w-0">
        <p className="font-semibold leading-snug">{titulo}</p>
        {children ? <div className="mt-1 text-sm soft">{children}</div> : null}
      </div>
    </div>
  );
}

/** Cifra con color semántico y signo: nunca solo color (siempre + / −). */
export function Variacion({ valor, children, className = "" }: { valor: number | null | undefined; children: ReactNode; className?: string }) {
  const t = tonoDe(valor);
  const flecha = t === "sube" ? "▲" : t === "baja" ? "▼" : "";
  return (
    <span className={`num ${t} ${className}`}>
      {flecha ? (
        <span aria-hidden="true" className="mr-1 text-[0.7em] align-[0.1em]">
          {flecha}
        </span>
      ) : null}
      {children}
    </span>
  );
}

export function SinCorrida() {
  const prox = proximaRevision();
  return (
    <div className="hoja entra mt-6 grid gap-4 p-6 sm:p-10">
      <p className="kicker">Todavía no hay datos</p>
      <p className="display text-3xl sm:text-4xl">El operador todavía no corrió.</p>
      <p className="max-w-xl soft">
        La primera revisión es <b>{prox.texto}</b>. Ahí va a analizar el mercado, armar tu cartera y contarte acá qué
        hizo y por qué. Si querés, podés pedirle que revise ahora desde <Link className="underline decoration-[var(--accent)] underline-offset-4" href="/configuracion#revisar">Configuración</Link>.
      </p>
    </div>
  );
}

export function Vacio({ titulo, children }: { titulo: string; children?: ReactNode }) {
  return (
    <div className="rounded-[var(--radius)] border border-dashed p-6 text-center" style={{ borderColor: "var(--line-strong)" }}>
      <p className="font-semibold">{titulo}</p>
      {children ? <p className="mx-auto mt-1 max-w-md text-sm muted">{children}</p> : null}
    </div>
  );
}

export function Descargo() {
  return (
    <p className="mt-16 border-t pt-4 text-xs muted" style={{ borderColor: "var(--line)" }}>
      Herramienta de análisis personal. No es asesoramiento financiero: las decisiones y el riesgo son tuyos.
    </p>
  );
}
