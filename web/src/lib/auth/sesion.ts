import "server-only";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { count, eq } from "drizzle-orm";
import { getDb, schema } from "../db";
import { COOKIE_SESION, DURACION_SESION_SEG, firmarSesion, verificarSesion } from "./token";

export async function cantidadUsuarios(): Promise<number> {
  const db = await getDb();
  const [r] = await db.select({ n: count() }).from(schema.usuarios);
  return Number(r?.n ?? 0);
}

export async function hayUsuario(): Promise<boolean> {
  return (await cantidadUsuarios()) > 0;
}

export async function borrarUsuario(email: string): Promise<void> {
  const db = await getDb();
  await db.delete(schema.usuarios).where(eq(schema.usuarios.email, email));
}

export async function usuarioPorEmail(email: string): Promise<{ email: string; hash: string } | null> {
  const db = await getDb();
  const [u] = await db.select().from(schema.usuarios).where(eq(schema.usuarios.email, email));
  return u ?? null;
}

export async function crearUsuario(email: string, hash: string): Promise<void> {
  const db = await getDb();
  await db.insert(schema.usuarios).values({ email, hash, creado: new Date().toISOString() });
}

export async function iniciarSesion(email: string): Promise<void> {
  const token = await firmarSesion(email, process.env.SESSION_SECRET);
  const jar = await cookies();
  jar.set(COOKIE_SESION, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: DURACION_SESION_SEG,
  });
}

export async function cerrarSesion(): Promise<void> {
  const jar = await cookies();
  jar.delete(COOKIE_SESION);
}

/** Email del dueño logueado o null. El middleware ya filtra, esto es la segunda barrera (acciones del servidor). */
export async function sesionActual(): Promise<string | null> {
  const jar = await cookies();
  const email = await verificarSesion(jar.get(COOKIE_SESION)?.value, process.env.SESSION_SECRET);
  if (!email) return null;
  return (await usuarioPorEmail(email)) ? email : null;
}

export async function exigirSesion(): Promise<string> {
  const email = await sesionActual();
  if (!email) redirect("/login");
  return email;
}

export async function ipCliente(): Promise<string> {
  const h = await headers();
  // En Vercel estos headers los pone la plataforma (pisa lo que mande el cliente).
  return (
    h.get("x-vercel-forwarded-for")?.split(",")[0]?.trim() ??
    h.get("x-real-ip") ??
    h.get("x-forwarded-for")?.split(",")[0]?.trim() ??
    "desconocida"
  );
}
