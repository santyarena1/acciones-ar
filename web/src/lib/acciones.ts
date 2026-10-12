import "server-only";
import { z } from "zod";
import { sesionActual } from "./auth/sesion";

/** Respuesta uniforme de las acciones del servidor (se muestra tal cual en pantalla). */
export interface Respuesta {
  ok: boolean;
  mensaje: string;
  errores?: Record<string, string>;
  /** Datos no secretos para mostrar (ej. código de vinculación). */
  datos?: Record<string, string>;
  /** Cambia en cada respuesta para que la UI pueda reaccionar aunque el texto se repita. */
  marca?: number;
}

export const INICIAL: Respuesta = { ok: false, mensaje: "" };

export function ok(mensaje: string): Respuesta {
  return { ok: true, mensaje, marca: Date.now() };
}

export function falla(mensaje: string, errores?: Record<string, string>): Respuesta {
  return { ok: false, mensaje, errores, marca: Date.now() };
}

export function erroresDe(e: z.ZodError): Record<string, string> {
  const out: Record<string, string> = {};
  for (const i of e.issues) {
    const k = String(i.path[0] ?? "_");
    out[k] ??= i.message;
  }
  return out;
}

/**
 * Envuelve una acción: exige sesión, valida el formulario con zod y nunca deja escapar detalles internos.
 */
export function accion<S extends z.ZodType>(
  esquema: S,
  fn: (datos: z.infer<S>) => Promise<Respuesta>,
): (previo: Respuesta, form: FormData) => Promise<Respuesta> {
  return async (_previo, form) => {
    if (!(await sesionActual())) return falla("Tu sesión venció. Volvé a entrar.");
    const crudo = Object.fromEntries(form.entries());
    const p = esquema.safeParse(crudo);
    if (!p.success) return falla("Revisá los datos marcados.", erroresDe(p.error));
    try {
      return await fn(p.data);
    } catch (e) {
      // solo el tipo de error: el mensaje de la base puede traer parámetros
      console.error("[accion] error:", e instanceof Error ? e.name : "desconocido");
      return falla("Algo salió mal. Probá de nuevo en un rato.");
    }
  };
}

/** Monto en pesos escrito a mano: acepta "500.000", "500000", "$ 1.234.567,50". */
export const montoSchema = z
  .string()
  .trim()
  .transform((s) => {
    const limpio = s.replace(/[$\s]/g, "").replace(/\./g, "").replace(",", ".");
    return limpio === "" ? Number.NaN : Number(limpio);
  })
  .pipe(
    z
      .number({ message: "Escribí un monto en números." })
      .finite("Escribí un monto en números.")
      .positive("Tiene que ser mayor a cero.")
      .max(1e12, "Ese monto es demasiado grande."),
  );
