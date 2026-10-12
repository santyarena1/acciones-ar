/** Esqueleto mientras carga cualquier pantalla: misma estructura que la página, sin saltos al aparecer. */
export default function Cargando() {
  return (
    <div aria-busy="true" aria-label="Cargando" className="pt-8 lg:pt-12">
      <div className="esqueleto h-3 w-40" />
      <div className="esqueleto mt-5 h-14 w-[min(26rem,85%)]" />
      <div className="esqueleto mt-3 h-4 w-64" />
      <div className="mt-10 grid gap-6 lg:grid-cols-2">
        <div className="esqueleto h-[260px] !rounded-[var(--radius)]" />
        <div className="grid gap-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="grid gap-2">
              <div className="esqueleto h-3.5 w-1/2" />
              <div className="esqueleto h-2.5 w-full" />
            </div>
          ))}
        </div>
      </div>
      <div className="mt-10 grid gap-3">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="esqueleto h-12 w-full" />
        ))}
      </div>
      <span className="sr-only">Cargando…</span>
    </div>
  );
}
