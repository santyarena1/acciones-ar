import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";
import { igualesSeguro } from "@/lib/auth/igualdad";
import { AYUDA, parsearComando, textoCartera, textoEstado, textoHoy } from "@/lib/domain/bot";
import { encolarComando } from "@/lib/data/comandos";
import { contextoDatos as contextoApp } from "@/lib/data/contexto";
import { guardarEstado } from "@/lib/data/estado";
import { eventosRecientes, registrarEvento } from "@/lib/data/eventos";
import { leerSecreto } from "@/lib/data/secretos";
import { diaAR } from "@/lib/format";
import { dispararOperador } from "@/lib/integraciones/github";
import { enviarMensaje } from "@/lib/integraciones/telegram";

export const dynamic = "force-dynamic";

const updateSchema = z.looseObject({
  message: z
    .looseObject({
      chat: z.looseObject({ id: z.union([z.number(), z.string()]) }),
      text: z.string().max(4096).optional(),
    })
    .optional(),
});

/**
 * Webhook del bot. Telegram manda el secreto en X-Telegram-Bot-Api-Secret-Token; solo se contesta al chat guardado.
 * Siempre responde 200 a Telegram (si no, reintenta) salvo que el secreto no coincida.
 */
export async function POST(req: NextRequest) {
  const secreto = process.env.TELEGRAM_WEBHOOK_SECRET;
  if (!secreto || secreto.length < 16 || !igualesSeguro(req.headers.get("x-telegram-bot-api-secret-token"), secreto)) {
    return new NextResponse(null, { status: 401 });
  }
  const p = updateSchema.safeParse(await req.json().catch(() => null));
  if (!p.success || !p.data.message) return NextResponse.json({ ok: true });

  const [token, chat] = await Promise.all([leerSecreto("TELEGRAM_TOKEN"), leerSecreto("TELEGRAM_CHAT_ID")]);
  const chatId = String(p.data.message.chat.id);
  if (!token || !chat || chatId !== chat) return NextResponse.json({ ok: true });

  try {
    const respuesta = await responder(parsearComando(p.data.message.text));
    await enviarMensaje(token, chat, respuesta);
  } catch (e) {
    console.error("[telegram] error al responder:", e instanceof Error ? e.name : "error");
    await enviarMensaje(token, chat, "Tuve un problema para contestarte. Probá de nuevo en un rato.");
  }
  return NextResponse.json({ ok: true });
}

async function responder(cmd: ReturnType<typeof parsearComando>): Promise<string> {
  switch (cmd) {
    case "estado":
      return textoEstado(await contextoApp());
    case "cartera":
      return textoCartera((await contextoApp()).corrida);
    case "hoy": {
      const ctx = await contextoApp();
      const hoy = diaAR(new Date());
      const desde = new Date(`${hoy}T00:00:00-03:00`).toISOString();
      const evs = await eventosRecientes({ tipos: ["orden", "aporte", "pedido_fondos", "descartada", "error", "aviso_caida"], modo: ctx.modo, desde, limite: 50 });
      return textoHoy(evs, ctx.corrida?.nombresRf);
    }
    case "pausar":
      await guardarEstado("pausado", { pausado: true, motivo: "manual" });
      await registrarEvento("pausa", { motivo: "Desde Telegram" });
      return "⏸ Listo, quedo en pausa. No compro ni vendo hasta que me digas /reanudar.";
    case "reanudar":
      await guardarEstado("pausado", { pausado: false, motivo: null });
      await registrarEvento("reanudar", {});
      return "▶ Listo, vuelvo a trabajar en la próxima revisión.";
    case "revisar": {
      await encolarComando("revisar");
      const r = await dispararOperador();
      return r === "disparado" ? "🔎 Arranco a revisar. En unos minutos te cuento." : "🔎 Anotado: reviso en la próxima vuelta (cada hora con el mercado abierto).";
    }
    case "ayuda":
      return AYUDA;
    default:
      return `No entendí. ${AYUDA}`;
  }
}

// "Revisar ahora" dispara el motor con after(): la función sigue viva hasta que termina (~1 min)
export const maxDuration = 300;
