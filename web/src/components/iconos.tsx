/** Íconos de trazo fino (1.6px), dibujados para esta app. Decorativos: aria-hidden. */
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;

function Base({ children, ...p }: P) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...p}>
      {children}
    </svg>
  );
}

export const IconoInicio = (p: P) => (
  <Base {...p}>
    <path d="M3.5 11.2 12 4l8.5 7.2" />
    <path d="M5.5 9.8V20h13V9.8" />
    <path d="M10 20v-5.5h4V20" />
  </Base>
);
export const IconoCartera = (p: P) => (
  <Base {...p}>
    <rect x="3" y="6.5" width="18" height="13" rx="2.5" />
    <path d="M8 6.5V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v1.5" />
    <path d="M3 12h18" />
  </Base>
);
export const IconoOportunidades = (p: P) => (
  <Base {...p}>
    <path d="M3 17.5 9 11.5l4 4 8-8" />
    <path d="M15 7.5h6v6" />
  </Base>
);
export const IconoBonos = (p: P) => (
  <Base {...p}>
    <path d="M6 3.5h9l3.5 3.5V20.5H6z" />
    <path d="M15 3.5V7h3.5" />
    <path d="M9 12h6M9 15.5h6" />
  </Base>
);
export const IconoHistorial = (p: P) => (
  <Base {...p}>
    <path d="M4 12a8 8 0 1 0 2.4-5.7" />
    <path d="M4 4.5v3.8h3.8" />
    <path d="M12 8v4.3l3 1.8" />
  </Base>
);
export const IconoAjustes = (p: P) => (
  <Base {...p}>
    <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />
    <circle cx="16" cy="7" r="2" />
    <circle cx="8" cy="17" r="2" />
  </Base>
);
export const IconoAlerta = (p: P) => (
  <Base {...p}>
    <path d="M12 4 21 19.5H3z" />
    <path d="M12 10v4.2M12 17h.01" />
  </Base>
);
export const IconoInfo = (p: P) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 11v5M12 8h.01" />
  </Base>
);
export const IconoPausa = (p: P) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M10 9v6M14 9v6" />
  </Base>
);
export const IconoPlay = (p: P) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="m10 8.8 5 3.2-5 3.2z" />
  </Base>
);
export const IconoPlata = (p: P) => (
  <Base {...p}>
    <rect x="2.5" y="6" width="19" height="12" rx="2" />
    <circle cx="12" cy="12" r="2.6" />
    <path d="M6 9.5v.01M18 14.5v.01" />
  </Base>
);
export const IconoCaida = (p: P) => (
  <Base {...p}>
    <path d="M3 6.5 9 12.5l4-4 8 8" />
    <path d="M15 16.5h6v-6" />
  </Base>
);
export const IconoFlecha = (p: P) => (
  <Base {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Base>
);
export const IconoAtras = (p: P) => (
  <Base {...p}>
    <path d="M19 12H5M11 6l-6 6 6 6" />
  </Base>
);
export const IconoSol = (p: P) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="3.8" />
    <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" />
  </Base>
);
export const IconoLuna = (p: P) => (
  <Base {...p}>
    <path d="M19.5 14.5A8 8 0 0 1 9.5 4.5a8 8 0 1 0 10 10z" />
  </Base>
);
export const IconoAuto = (p: P) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 3.5v17" />
    <path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor" stroke="none" />
  </Base>
);
export const IconoSalir = (p: P) => (
  <Base {...p}>
    <path d="M14 4.5h4.5v15H14" />
    <path d="M10 8l-4 4 4 4M6 12h9" />
  </Base>
);
export const IconoCheck = (p: P) => (
  <Base {...p}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </Base>
);
export const IconoBuscar = (p: P) => (
  <Base {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m20 20-4.2-4.2" />
  </Base>
);
export const IconoRefrescar = (p: P) => (
  <Base {...p}>
    <path d="M20 12a8 8 0 0 1-14.3 4.9M4 12a8 8 0 0 1 14.3-4.9" />
    <path d="M18.5 3.5v3.8h-3.8M5.5 20.5v-3.8h3.8" />
  </Base>
);
export const IconoCandado = (p: P) => (
  <Base {...p}>
    <rect x="5" y="10.5" width="14" height="10" rx="2" />
    <path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" />
  </Base>
);
export const IconoChat = (p: P) => (
  <Base {...p}>
    <path d="M20.5 4 3.5 11l6 2.2L12 20l8.5-16z" />
    <path d="m9.5 13.2 4-3.2" />
  </Base>
);

/** Monograma de la app: una "A" de libro mayor sobre una línea base. */
export function Monograma({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect x="0.5" y="0.5" width="31" height="31" rx="9" fill="var(--ink)" />
      <path d="M9 22.5 16 8.5l7 14" fill="none" stroke="var(--bg-sheet)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M11.6 17.5h8.8" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
      <path d="M7 25.5h18" stroke="var(--bg-sheet)" strokeOpacity=".35" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}
