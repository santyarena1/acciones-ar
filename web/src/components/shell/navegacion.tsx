"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  IconoAjustes,
  IconoBonos,
  IconoCartera,
  IconoHistorial,
  IconoInicio,
  IconoOportunidades,
} from "../iconos";

const ITEMS = [
  { href: "/", corto: "Inicio", largo: "Inicio", Icono: IconoInicio, enTab: true },
  { href: "/cartera", corto: "Cartera", largo: "Mi cartera", Icono: IconoCartera, enTab: true },
  { href: "/oportunidades", corto: "Mercado", largo: "Oportunidades", Icono: IconoOportunidades, enTab: true },
  { href: "/bonos", corto: "Bonos", largo: "Bonos y letras", Icono: IconoBonos, enTab: false },
  { href: "/historial", corto: "Historial", largo: "Historial", Icono: IconoHistorial, enTab: true },
  { href: "/configuracion", corto: "Ajustes", largo: "Configuración", Icono: IconoAjustes, enTab: true },
] as const;

function activo(path: string, href: string): boolean {
  if (href === "/") return path === "/";
  if (href === "/oportunidades") return path.startsWith("/oportunidades") || path.startsWith("/bonos") || path.startsWith("/activo");
  return path.startsWith(href);
}

export function NavRail() {
  const path = usePathname();
  return (
    <nav aria-label="Secciones" className="mt-8 grid gap-1">
      {ITEMS.map(({ href, largo, Icono }) => {
        const on = href === "/oportunidades" ? path.startsWith("/oportunidades") || path.startsWith("/activo") : activo(path, href);
        return (
          <Link key={href} href={href} className="rail-link" aria-current={on ? "page" : undefined}>
            <Icono />
            {largo}
          </Link>
        );
      })}
    </nav>
  );
}

export function TabBar() {
  const path = usePathname();
  return (
    <nav aria-label="Secciones" className="tabbar">
      {ITEMS.filter((i) => i.enTab).map(({ href, corto, Icono }) => (
        <Link key={href} href={href} className="tab" aria-current={activo(path, href) ? "page" : undefined}>
          <Icono />
          {corto}
        </Link>
      ))}
    </nav>
  );
}
