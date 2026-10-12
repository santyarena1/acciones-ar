import { redirect } from "next/navigation";
import { entrar } from "@/app/acciones/auth";
import { BotonEnviar, Campo, FormAccion } from "@/components/ui/formulario";
import { hayUsuario, sesionActual } from "@/lib/auth/sesion";

export const metadata = { title: "Entrar" };

export default async function Login({ searchParams }: { searchParams: Promise<{ volver?: string }> }) {
  if (!(await hayUsuario())) redirect("/setup");
  if (await sesionActual()) redirect("/");
  const { volver } = await searchParams;
  return (
    <div className="hoja entra p-6 sm:p-8" style={{ ["--i" as string]: 1 }}>
      <h1 className="display text-[2.2rem]">Hola de nuevo</h1>
      <p className="mt-1 text-sm muted">Entrá para ver cómo va tu cartera.</p>
      <FormAccion accion={entrar} className="mt-6 grid gap-4" aria-label="Ingreso">
        <input type="hidden" name="volver" value={volver ?? ""} />
        <Campo nombre="email" etiqueta="Email" type="email" autoComplete="username" inputMode="email" required autoFocus />
        <Campo nombre="clave" etiqueta="Contraseña" type="password" autoComplete="current-password" required />
        <BotonEnviar className="btn btn-primario mt-2 w-full" pendiente="Entrando…">
          Entrar
        </BotonEnviar>
      </FormAccion>
    </div>
  );
}
