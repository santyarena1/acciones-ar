import "server-only";
import { createHmac } from "node:crypto";
import { z } from "zod";

/** Cliente mínimo de la API de bots de Telegram. El token nunca se loguea ni se devuelve. */
const TIMEOUT_MS = 10_000;

export const tokenTelegramSchema = z
  .string()
  .trim()
  .regex(/^\d{5,15}:[A-Za-z0-9_-]{30,60}$/, "Ese token no tiene la forma que da @BotFather (números:letras).");

const respuestaSchema = z.looseObject({ ok: z.boolean(), result: z.unknown().optional(), description: z.string().optional() });

async function llamar(token: string, metodo: string, cuerpo?: Record<string, unknown>): Promise<z.infer<typeof respuestaSchema>> {
  const r = await fetch(`https://api.telegram.org/bot${token}/${metodo}`, {
    method: cuerpo ? "POST" : "GET",
    headers: cuerpo ? { "Content-Type": "application/json" } : undefined,
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
    signal: AbortSignal.timeout(TIMEOUT_MS),
    cache: "no-store",
  });
  const json: unknown = await r.json().catch(() => ({ ok: false }));
  const p = respuestaSchema.safeParse(json);
  return p.success ? p.data : { ok: false };
}

const updatesSchema = z.array(
  z.looseObject({
    message: z
      .looseObject({
        chat: z.looseObject({ id: z.number(), first_name: z.string().optional(), type: z.string().optional() }),
        text: z.string().optional(),
      })
      .optional(),
  }),
);

export type ResultadoChat = { ok: true; chatId: string; nombre: string | null } | { ok: false; motivo: string };

/**
 * Código de vinculación de un solo bot: HMAC del token con un secreto del servidor (sin guardar nada).
 * Solo se vincula el chat que le manda este código al bot: el usuario del bot es público y cualquiera podría
 * escribirle /start antes que el dueño.
 */
export function codigoVinculo(token: string, secreto: string | undefined): string {
  if (!secreto) throw new Error("Falta SESSION_SECRET.");
  return createHmac("sha256", secreto).update(`telegram:${token}`).digest("hex").slice(0, 8).toUpperCase();
}

export async function nombreBot(token: string): Promise<string | null> {
  try {
    const me = await llamar(token, "getMe");
    const u = (me.result as { username?: unknown } | undefined)?.username;
    return me.ok && typeof u === "string" ? u : null;
  } catch {
    return null;
  }
}

/** Busca el chat privado que le mandó al bot el código de vinculación. */
export async function buscarChat(token: string, codigo: string): Promise<ResultadoChat> {
  try {
    const me = await llamar(token, "getMe");
    if (!me.ok) return { ok: false, motivo: "Telegram no reconoce ese token. Copialo de nuevo desde @BotFather." };
    const r = await llamar(token, "getUpdates");
    if (!r.ok) {
      return { ok: false, motivo: "El bot ya está conectado a esta app (webhook). Si querés cambiar de chat, quitá la conexión y volvé a buscar." };
    }
    const ups = updatesSchema.safeParse(r.result);
    const ultimo = ups.success
      ? [...ups.data].reverse().find((u) => u.message?.chat.type === "private" && (u.message.text ?? "").toUpperCase().includes(codigo))
      : undefined;
    if (!ultimo?.message) {
      return { ok: false, motivo: `Todavía no encuentro tu mensaje. Mandale al bot exactamente: /start ${codigo} y volvé a tocar “Buscar mi chat”.` };
    }
    return { ok: true, chatId: String(ultimo.message.chat.id), nombre: ultimo.message.chat.first_name ?? null };
  } catch {
    return { ok: false, motivo: "No pude comunicarme con Telegram. Probá de nuevo." };
  }
}

export async function enviarMensaje(token: string, chatId: string, texto: string): Promise<boolean> {
  try {
    const r = await llamar(token, "sendMessage", { chat_id: chatId, text: texto, parse_mode: "HTML", disable_web_page_preview: true });
    return r.ok;
  } catch {
    return false;
  }
}

export async function registrarWebhook(token: string, url: string, secreto: string): Promise<{ ok: boolean; motivo?: string }> {
  try {
    const r = await llamar(token, "setWebhook", { url, secret_token: secreto, allowed_updates: ["message"], drop_pending_updates: true });
    return r.ok ? { ok: true } : { ok: false, motivo: r.description ?? "Telegram rechazó la conexión." };
  } catch {
    return { ok: false, motivo: "No pude comunicarme con Telegram." };
  }
}

export async function quitarWebhook(token: string): Promise<boolean> {
  try {
    return (await llamar(token, "deleteWebhook", {})).ok;
  } catch {
    return false;
  }
}

