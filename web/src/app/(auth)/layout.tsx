import { Monograma } from "@/components/iconos";

/** Pantallas de acceso: una hoja centrada sobre el papel, con la marca arriba. */
export default function LayoutAcceso({ children }: { children: React.ReactNode }) {
  return (
    <main className="relative z-[1] grid min-h-dvh place-items-center px-4 py-10">
      <div className="w-full max-w-[420px]">
        <div className="entra mb-8 flex items-center gap-3">
          <Monograma size={36} />
          <div>
            <p className="display text-[1.6rem] leading-none">Operador</p>
            <p className="kicker mt-1 !text-[0.62rem]">Tu cartera en IOL, en piloto automático</p>
          </div>
        </div>
        {children}
        <p className="mt-8 text-center text-xs muted">Acceso privado. No es asesoramiento financiero.</p>
      </div>
    </main>
  );
}
