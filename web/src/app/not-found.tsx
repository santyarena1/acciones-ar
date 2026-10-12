import Link from "next/link";

export default function NoEncontrado() {
  return (
    <main className="relative z-[1] grid min-h-[70dvh] place-items-center px-4">
      <div className="text-center">
        <p className="display num text-[6rem] leading-none" style={{ color: "var(--accent)" }}>
          404
        </p>
        <p className="mt-2 text-lg">No encontramos eso.</p>
        <p className="mt-1 text-sm muted">Puede que el activo ya no esté en el análisis.</p>
        <Link href="/" className="btn btn-primario mt-6">
          Volver al inicio
        </Link>
      </div>
    </main>
  );
}
