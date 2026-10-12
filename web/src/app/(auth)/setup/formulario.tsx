"use client";

import { crearDueno } from "@/app/acciones/auth";
import { BotonEnviar, Campo, FormAccion } from "@/components/ui/formulario";

export function FormularioSetup() {
  return (
    <FormAccion accion={crearDueno} className="mt-6 grid gap-4" aria-label="Crear cuenta">
      {(e) => (
        <>
          <Campo nombre="token" etiqueta="Código de instalación" type="password" autoComplete="off" required error={e.errores?.token} />
          <Campo nombre="email" etiqueta="Tu email" type="email" autoComplete="username" inputMode="email" required error={e.errores?.email} />
          <Campo
            nombre="clave"
            etiqueta="Contraseña nueva"
            type="password"
            autoComplete="new-password"
            minLength={10}
            required
            error={e.errores?.clave}
            ayuda="Mínimo 10 caracteres. Una frase larga es más fácil de recordar y más segura."
          />
          <Campo nombre="clave2" etiqueta="Repetí la contraseña" type="password" autoComplete="new-password" required error={e.errores?.clave2} />
          <BotonEnviar className="btn btn-primario mt-2 w-full" pendiente="Creando…">
            Crear acceso y entrar
          </BotonEnviar>
        </>
      )}
    </FormAccion>
  );
}
