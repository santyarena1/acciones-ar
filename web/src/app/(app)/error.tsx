"use client";

export default function ErrorPantalla({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="hoja mt-10 grid gap-4 p-6 sm:p-10">
      <p className="kicker">Algo salió mal</p>
      <p className="display text-3xl">No pudimos cargar esta pantalla.</p>
      <p className="max-w-lg soft">Puede ser un problema momentáneo de conexión con la base. Tus inversiones no se tocan por esto.</p>
      <div>
        <button type="button" className="btn btn-primario" onClick={reset}>
          Probar de nuevo
        </button>
      </div>
    </div>
  );
}
