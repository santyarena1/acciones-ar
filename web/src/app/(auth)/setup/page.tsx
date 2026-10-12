import { redirect } from "next/navigation";
import { hayUsuario } from "@/lib/auth/sesion";
import { FormularioSetup } from "./formulario";

export const metadata = { title: "Primera vez" };

export default async function Setup() {
  if (await hayUsuario()) redirect("/login");
  return (
    <div className="hoja entra p-6 sm:p-8" style={{ ["--i" as string]: 1 }}>
      <p className="kicker">Primera vez</p>
      <h1 className="display mt-1 text-[2.2rem]">Creá tu acceso</h1>
      <p className="mt-1 text-sm muted">
        Solo se hace una vez. Vas a necesitar el código de instalación que configuró quien te armó el sistema.
      </p>
      <FormularioSetup />
    </div>
  );
}
