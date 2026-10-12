"use server";

import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { accion, falla, ok } from "@/lib/acciones";
import { borrarSecretos, guardarSecretos, leerSecreto } from "@/lib/data/secretos";
import { leerPreferencias, modoDe } from "@/lib/data/preferencias";
import { registrarEvento } from "@/lib/data/eventos";
import { plata } from "@/lib/format";
import { probarIol } from "@/lib/integraciones/iol";
import {
  buscarChat,
  codigoVinculo,
  enviarMensaje,
  nombreBot,
  quitarWebhook,
  registrarWebhook,
  tokenTelegramSchema,
} from "@/lib/integraciones/telegram";

const iolSchema = z.object({
  usuario: z.string().trim().min(3, "Escribí tu usuario de IOL.").max(120),
  clave: z.string().min(4, "Escribí tu contraseña de IOL.").max(200),
});

/** Prueba la conexión y SOLO si anda guarda usuario y contraseña cifrados. */
export const conectarIol = accion(iolSchema, async ({ usuario, clave }) => {
  const r = await probarIol(usuario, clave);
  if (!r.ok) return falla(r.motivo);
  await guardarSecretos({ IOL_USERNAME: usuario, IOL_PASSWORD: clave });
  await registrarEvento("comando", { texto: "Conectaste tu cuenta de IOL" });
  revalidatePath("/configuracion");
  const saldo = r.totalPesos !== null ? ` Tu cuenta vale ${plata(r.totalPesos)}` : "";
  const disp = r.disponiblePesos !== null ? ` y tenés ${plata(r.disponiblePesos)} disponibles.` : saldo ? "." : "";
  return ok(`¡Conectado! IOL respondió bien.${saldo}${disp} Guardamos tus datos cifrados.`);
});

export const probarIolGuardado = accion(z.object({}), async () => {
  const [u, c] = await Promise.all([leerSecreto("IOL_USERNAME"), leerSecreto("IOL_PASSWORD")]);
  if (!u || !c) return falla("Todavía no conectaste tu cuenta de IOL.");
  const r = await probarIol(u, c);
  if (!r.ok) return falla(r.motivo);
  return ok(`La conexión anda bien.${r.totalPesos !== null ? ` Tu cuenta vale ${plata(r.totalPesos)}.` : ""}`);
});

export const desconectarIol = accion(z.object({}), async () => {
  if (modoDe(await leerPreferencias()) === "live") {
    return falla("Estás en modo real. Primero volvé a modo práctica y después desconectá IOL.");
  }
  await borrarSecretos(["IOL_USERNAME", "IOL_PASSWORD"]);
  revalidatePath("/configuracion");
  return ok("Listo: borramos tus datos de IOL.");
});

/** Paso 1: valida el token y devuelve el código que el dueño le tiene que mandar a su bot. */
export const prepararTelegram = accion(z.object({ token: tokenTelegramSchema }), async ({ token }) => {
  const bot = await nombreBot(token);
  if (!bot) return falla("Telegram no reconoce ese token. Copialo de nuevo desde @BotFather.");
  const codigo = codigoVinculo(token, process.env.SESSION_SECRET);
  return { ...ok(`Ahora mandale a @${bot} este mensaje: /start ${codigo}`), datos: { codigo, bot } };
});

/** Paso 2: vincula SOLO el chat que le mandó el código al bot (el usuario del bot es público). */
export const buscarChatTelegram = accion(z.object({ token: tokenTelegramSchema }), async ({ token }) => {
  const r = await buscarChat(token, codigoVinculo(token, process.env.SESSION_SECRET));
  if (!r.ok) return falla(r.motivo);
  await guardarSecretos({ TELEGRAM_TOKEN: token, TELEGRAM_CHAT_ID: r.chatId });
  await enviarMensaje(token, r.chatId, "Hola 👋 Ya estoy conectado. Te voy a avisar acá cuando el operador compre, venda o necesite algo.");
  revalidatePath("/configuracion");
  return ok(`¡Encontrado${r.nombre ? `, ${r.nombre}` : ""}! Te mandé un mensaje de bienvenida a Telegram.`);
});

async function credencialesTelegram(): Promise<{ token: string; chat: string } | null> {
  const [token, chat] = await Promise.all([leerSecreto("TELEGRAM_TOKEN"), leerSecreto("TELEGRAM_CHAT_ID")]);
  return token && chat ? { token, chat } : null;
}

export const probarTelegram = accion(z.object({}), async () => {
  const c = await credencialesTelegram();
  if (!c) return falla("Primero conectá tu bot (pasos de arriba).");
  const enviado = await enviarMensaje(c.token, c.chat, "Mensaje de prueba del operador ✅ Si lo ves, los avisos funcionan.");
  return enviado ? ok("Mensaje enviado. Fijate en Telegram.") : falla("Telegram no aceptó el mensaje. Volvé a buscar tu chat.");
});

/** En producción solo se confía en APP_URL o en el dominio de producción que informa Vercel (nunca en headers). */
async function urlPublica(): Promise<string | null> {
  const app = process.env.APP_URL;
  if (app) return /^https:\/\//.test(app) ? app.replace(/\/$/, "") : null;
  if (process.env.VERCEL_PROJECT_PRODUCTION_URL) return `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`;
  if (process.env.NODE_ENV === "production") return null;
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host");
  if (!host || /^(localhost|127\.|\[::1\])/.test(host)) return null;
  return `https://${host}`;
}

export const conectarWebhook = accion(z.object({}), async () => {
  const secreto = process.env.TELEGRAM_WEBHOOK_SECRET;
  if (!secreto || !/^[A-Za-z0-9_-]{16,256}$/.test(secreto)) {
    return falla("Falta configurar TELEGRAM_WEBHOOK_SECRET en el servidor (letras, números, _ o -, mínimo 16).");
  }
  const c = await credencialesTelegram();
  if (!c) return falla("Primero conectá tu bot (pasos de arriba).");
  const base = await urlPublica();
  if (!base) return falla("Esto funciona solo con la app publicada en internet (no en la computadora local).");
  const r = await registrarWebhook(c.token, `${base}/api/telegram`, secreto);
  if (!r.ok) return falla(`Telegram no aceptó la conexión: ${r.motivo ?? "sin detalle"}.`);
  await enviarMensaje(c.token, c.chat, "Listo: ahora podés escribirme /estado, /cartera, /hoy, /pausar, /reanudar o /revisar.");
  return ok("¡Listo! Ya podés escribirle comandos al bot. Probá con /estado.");
});

export const desconectarTelegram = accion(z.object({}), async () => {
  const token = await leerSecreto("TELEGRAM_TOKEN");
  if (token) await quitarWebhook(token);
  await borrarSecretos(["TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]);
  revalidatePath("/configuracion");
  return ok("Listo: el bot quedó desconectado.");
});
