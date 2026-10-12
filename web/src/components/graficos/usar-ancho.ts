"use client";

import { useEffect, useRef, useState } from "react";

/** Ancho del contenedor (para que el SVG dibuje a tamaño real y el texto no se deforme). */
export function useAncho<T extends HTMLElement>(inicial = 600) {
  const ref = useRef<T>(null);
  const [ancho, setAncho] = useState(inicial);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      if (e) setAncho(Math.max(240, Math.round(e.contentRect.width)));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, ancho };
}
