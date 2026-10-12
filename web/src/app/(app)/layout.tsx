import Link from "next/link";
import { salir } from "@/app/acciones/auth";
import { IconoSalir, Monograma } from "@/components/iconos";
import { BloqueEstado, PastillasEstado } from "@/components/shell/estado-operador";
import { NavRail, TabBar } from "@/components/shell/navegacion";
import { SelectorTema } from "@/components/shell/tema";
import { exigirSesion } from "@/lib/auth/sesion";
import { contextoApp } from "@/lib/data/contexto";

export default async function LayoutApp({ children }: { children: React.ReactNode }) {
  await exigirSesion();
  const ctx = await contextoApp();
  return (
    <div className="shell">
      <a href="#principal" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 btn">
        Saltar al contenido
      </a>
      <aside className="rail-col" aria-label="Menú">
        <div className="rail">
        <Link href="/" className="flex items-center gap-3 px-2" aria-label="Inicio">
          <Monograma />
          <span className="leading-tight">
            <span className="display block text-[1.35rem]">Operador</span>
            <span className="kicker !text-[0.6rem]">Banca personal</span>
          </span>
        </Link>
        <NavRail />
        <div className="mt-auto grid gap-3">
          <BloqueEstado ctx={ctx} />
          <div className="flex items-center justify-between px-1">
            <SelectorTema />
            <form action={salir}>
              <button type="submit" className="btn btn-chico btn-texto muted" title="Salir">
                <IconoSalir width={17} height={17} />
                <span className="text-xs">Salir</span>
              </button>
            </form>
          </div>
        </div>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="topbar">
          <Link href="/" className="flex items-center gap-2.5" aria-label="Inicio">
            <Monograma size={26} />
            <span className="display text-[1.2rem]">Operador</span>
          </Link>
          <div className="flex items-center gap-1">
            <PastillasEstado ctx={ctx} compacto />
            <SelectorTema compacto />
          </div>
        </header>
        <main id="principal" className="contenido">
          {children}
        </main>
      </div>
      <TabBar />
    </div>
  );
}
