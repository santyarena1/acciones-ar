"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { falla, type Respuesta } from "@/lib/acciones";
import { evaluarIntentos, VENTANA_MS } from "@/lib/auth/limite";
import { huellaIp, igualesSeguro } from "@/lib/auth/igualdad";
import { claveNuevaSchema, coincide, emailSchema, hashear } from "@/lib/auth/password";
import {
  borrarUsuario,
  cantidadUsuarios,
  cerrarSesion,
  crearUsuario,
  hayUsuario,
  iniciarSesion,
  ipCliente,
  usuarioPorEmail,
} from "@/lib/auth/sesion";
import { loginsFallidos, registrarEvento } from "@/lib/data/eventos";

const loginSchema = z.object({
  email: emailSchema,
  clave: z.string().min(1, "Escribí tu contraseña.").max(200),
  volver: z.string().optional(),
});

/** Solo rutas internas (evita redirecciones abiertas). */
function destinoSeguro(v: string | undefined): string {
  return v && /^\/(?!\/)[\w\-/]*$/.test(v) ? v : "/";
}

// hash de relleno: compara igual aunque el email no exista (no revela si existe por el tiempo)
let hashRelleno: Promise<string> | undefined;
function relleno(): Promise<string> {
  hashRelleno ??= hashear(crypto.randomUUID());
  return hashRelleno;
}

/** Intentos fallidos recientes, por IP (hasheada) y por cuenta (email hasheado). */
async function limite(ip: string, cuenta: string): Promise<Respuesta | null> {
  const desde = new Date(Date.now() - VENTANA_MS).toISOString();
  const filas = await loginsFallidos(desde);
  const porIp = filas.map((f) => ({ ip: String(f.datos.ip ?? ""), ts: new Date(f.ts).getTime() }));
  const porCuenta = filas.map((f) => ({ ip: String(f.datos.cuenta ?? ""), ts: new Date(f.ts).getTime() }));
  for (const v of [evaluarIntentos(porIp, ip), evaluarIntentos(porCuenta, cuenta)]) {
    if (!v.permitido) {
      return falla(`Demasiados intentos. Esperá ${v.reintentarEnMin} ${v.reintentarEnMin === 1 ? "minuto" : "minutos"} y probá de nuevo.`);
    }
  }
  return null;
}

export async function entrar(_p: Respuesta, form: FormData): Promise<Respuesta> {
  const p = loginSchema.safeParse(Object.fromEntries(form.entries()));
  if (!p.success) return falla("Completá email y contraseña.");
  const sal = process.env.SESSION_SECRET ?? "";
  const ip = huellaIp(await ipCliente(), sal);
  const cuenta = huellaIp(`email:${p.data.email}`, sal);
  const bloqueo = await limite(ip, cuenta);
  if (bloqueo) return bloqueo;
  const u = await usuarioPorEmail(p.data.email);
  const valida = await coincide(p.data.clave, u?.hash ?? (await relleno()));
  if (!u || !valida) {
    await registrarEvento("login_fallido", { ip, cuenta });
    return falla("Email o contraseña incorrectos.");
  }
  await iniciarSesion(u.email);
  redirect(destinoSeguro(p.data.volver));
}

const setupSchema = z
  .object({
    token: z.string().min(1, "Falta el código de instalación."),
    email: emailSchema,
    clave: claveNuevaSchema,
    clave2: z.string(),
  })
  .refine((d) => d.clave === d.clave2, { path: ["clave2"], message: "Las contraseñas no coinciden." });

const MIN_SETUP_TOKEN = 24;

export async function crearDueno(_p: Respuesta, form: FormData): Promise<Respuesta> {
  if (await hayUsuario()) return falla("La cuenta ya existe. Entrá desde la pantalla de ingreso.");
  const esperado = process.env.SETUP_TOKEN;
  if (!esperado || esperado.length < MIN_SETUP_TOKEN) {
    return falla(`Falta configurar SETUP_TOKEN en el servidor (mínimo ${MIN_SETUP_TOKEN} caracteres).`);
  }
  const ip = huellaIp(await ipCliente(), esperado);
  const bloqueo = await limite(ip, "setup");
  if (bloqueo) return bloqueo;
  const p = setupSchema.safeParse(Object.fromEntries(form.entries()));
  if (!p.success) {
    const errores: Record<string, string> = {};
    for (const i of p.error.issues) errores[String(i.path[0])] ??= i.message;
    return falla("Revisá los datos marcados.", errores);
  }
  if (!igualesSeguro(p.data.token, esperado)) {
    await registrarEvento("login_fallido", { ip, cuenta: "setup" });
    return falla("El código de instalación no es correcto.", { token: "Código incorrecto." });
  }
  await crearUsuario(p.data.email, await hashear(p.data.clave));
  // un solo dueño: si dos altas corrieron a la vez, la que sobra se deshace
  if ((await cantidadUsuarios()) > 1) {
    await borrarUsuario(p.data.email);
    return falla("La cuenta ya existe. Entrá desde la pantalla de ingreso.");
  }
  await iniciarSesion(p.data.email);
  redirect("/");
}

export async function salir(): Promise<void> {
  await cerrarSesion();
  redirect("/login");
}
