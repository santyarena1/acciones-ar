"use client";

import { useActionState, useEffect, useRef, type ReactNode } from "react";
import { useFormStatus } from "react-dom";
import type { Respuesta } from "@/lib/acciones";
import { IconoAlerta, IconoCheck } from "../iconos";

type Accion = (previo: Respuesta, form: FormData) => Promise<Respuesta>;

interface Props {
  accion: Accion;
  children: ReactNode | ((estado: Respuesta) => ReactNode);
  className?: string;
  /** Limpia los campos cuando la acción sale bien (por ej. contraseñas). */
  limpiarAlOk?: boolean;
  "aria-label"?: string;
}

const INICIAL: Respuesta = { ok: false, mensaje: "" };

/** Formulario conectado a una acción del servidor, con mensaje accesible de resultado. */
export function FormAccion({ accion, children, className, limpiarAlOk, ...rest }: Props) {
  const [estado, enviar] = useActionState(accion, INICIAL);
  const ref = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (estado.ok && limpiarAlOk) ref.current?.reset();
  }, [estado, limpiarAlOk]);
  return (
    <form ref={ref} action={enviar} className={className} aria-label={rest["aria-label"]} noValidate>
      {typeof children === "function" ? children(estado) : children}
      <Mensaje estado={estado} />
    </form>
  );
}

export function Mensaje({ estado }: { estado: Respuesta }) {
  return (
    <div aria-live="polite" role="status" className="empty:hidden">
      {estado.mensaje ? (
        <p key={estado.marca} className="entra mt-3 flex items-start gap-2 text-sm" style={{ color: estado.ok ? "var(--gain)" : "var(--loss)" }}>
          {estado.ok ? <IconoCheck width={16} height={16} className="mt-0.5 flex-none" /> : <IconoAlerta width={16} height={16} className="mt-0.5 flex-none" />}
          <span>{estado.mensaje}</span>
        </p>
      ) : null}
    </div>
  );
}

export function BotonEnviar({ children, className = "btn btn-primario", pendiente, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { pendiente?: string }) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className={className} disabled={pending || p.disabled} aria-busy={pending} {...p}>
      {pending ? (
        <>
          <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-r-transparent" aria-hidden="true" />
          {pendiente ?? "Un momento…"}
        </>
      ) : (
        children
      )}
    </button>
  );
}

export function Campo({
  nombre,
  etiqueta,
  error,
  ayuda,
  ...input
}: React.InputHTMLAttributes<HTMLInputElement> & { nombre: string; etiqueta: string; error?: string; ayuda?: ReactNode }) {
  const id = `campo-${nombre}`;
  return (
    <div className="campo">
      <label htmlFor={id}>{etiqueta}</label>
      <input
        id={id}
        name={nombre}
        className="input"
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-err` : ayuda ? `${id}-ayuda` : undefined}
        {...input}
      />
      {error ? (
        <p id={`${id}-err`} className="error-campo">
          {error}
        </p>
      ) : ayuda ? (
        <p id={`${id}-ayuda`} className="ayuda">
          {ayuda}
        </p>
      ) : null}
    </div>
  );
}
