"use client";

import { useEffect, useState } from "react";
import { IconoAuto, IconoLuna, IconoSol } from "../iconos";

type Tema = "system" | "light" | "dark";
const OPCIONES: { v: Tema; label: string; Icono: typeof IconoSol }[] = [
  { v: "system", label: "Automático", Icono: IconoAuto },
  { v: "light", label: "Claro", Icono: IconoSol },
  { v: "dark", label: "Oscuro", Icono: IconoLuna },
];

function leerCookie(): Tema {
  const m = document.cookie.match(/(?:^|; )tema=(light|dark)/);
  return (m?.[1] as Tema | undefined) ?? "system";
}

/** Claro / oscuro / automático (sigue al teléfono). Se guarda en una cookie para que el servidor lo pinte bien. */
export function SelectorTema({ compacto = false }: { compacto?: boolean }) {
  const [tema, setTema] = useState<Tema>("system");
  useEffect(() => setTema(leerCookie()), []);

  function elegir(t: Tema) {
    setTema(t);
    const root = document.documentElement;
    if (t === "system") {
      root.removeAttribute("data-theme");
      document.cookie = "tema=; Path=/; Max-Age=0; SameSite=Lax";
    } else {
      root.setAttribute("data-theme", t);
      document.cookie = `tema=${t}; Path=/; Max-Age=31536000; SameSite=Lax`;
    }
  }

  if (compacto) {
    const i = OPCIONES.findIndex((o) => o.v === tema);
    const sig = OPCIONES[(i + 1) % OPCIONES.length]!;
    const Actual = OPCIONES[i]?.Icono ?? IconoAuto;
    return (
      <button
        type="button"
        className="btn btn-chico btn-texto"
        onClick={() => elegir(sig.v)}
        aria-label={`Tema: ${OPCIONES[i]?.label ?? "Automático"}. Cambiar a ${sig.label.toLowerCase()}`}
      >
        <Actual width={18} height={18} />
      </button>
    );
  }

  return (
    <div className="segmentado" role="radiogroup" aria-label="Tema">
      {OPCIONES.map(({ v, label, Icono }) => (
        <button key={v} type="button" role="radio" aria-checked={tema === v} onClick={() => elegir(v)} title={label}>
          <Icono width={15} height={15} />
          <span className="sr-only">{label}</span>
        </button>
      ))}
    </div>
  );
}
