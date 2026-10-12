"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { accion, falla, montoSchema, ok } from "@/lib/acciones";
import { encolarComando } from "@/lib/data/comandos";
import { guardarEstado, leerClaveEstado } from "@/lib/data/estado";
import { registrarEvento } from "@/lib/data/eventos";
import { guardarPreferencias, leerPreferencias, modoDe } from "@/lib/data/preferencias";
import { secretosCargados } from "@/lib/data/secretos";
import { plata } from "@/lib/format";
import { dispararOperador } from "@/lib/integraciones/github";
import { PERFILES, nombrePerfil } from "@/lib/perfiles";

const nada = z.object({});

function refrescar() {
  revalidatePath("/", "layout");
}

export const pausar = accion(nada, async () => {
  await guardarEstado("pausado", { pausado: true, motivo: "manual" });
  await registrarEvento("pausa", { motivo: "Desde la app" });
  refrescar();
  return ok("Listo: el operador queda en pausa. No compra ni vende hasta que lo reanudes.");
});

export const reanudar = accion(nada, async () => {
  await guardarEstado("pausado", { pausado: false, motivo: null });
  await registrarEvento("reanudar", {});
  refrescar();
  return ok("Listo: el operador vuelve a trabajar en la próxima revisión.");
});

export const revisarAhora = accion(nada, async () => {
  await encolarComando("revisar");
  const r = await dispararOperador();
  refrescar();
  if (r === "disparado") return ok("Pedido enviado. En 2 o 3 minutos vas a ver la revisión nueva.");
  if (r === "fallo") return ok("Lo anoté, pero no pude arrancarlo ya: se hace en la próxima revisión automática (cada hora con el mercado abierto).");
  return ok("Lo anoté: se hace en la próxima revisión automática (cada hora con el mercado abierto).");
});

const perfilSchema = z.object({
  perfil: z.enum(PERFILES.map((p) => p.id) as [string, ...string[]], { message: "Elegí un perfil." }),
});

export const cambiarPerfil = accion(perfilSchema, async ({ perfil }) => {
  await guardarPreferencias({ operador: { perfil } });
  refrescar();
  return ok(`Perfil cambiado a ${nombrePerfil(perfil)}. Se aplica en la próxima revisión.`);
});

export const depositarPractica = accion(z.object({ monto: montoSchema }), async ({ monto }) => {
  const modo = modoDe(await leerPreferencias());
  if (modo !== "paper") return falla("En modo real la plata se ingresa transfiriendo a tu cuenta de IOL.");
  await encolarComando("depositar_practica", { monto: Math.round(monto) });
  refrescar();
  return ok(`Anotado: se suman ${plata(monto)} a la cuenta de práctica en la próxima revisión.`);
});

export const reiniciarPractica = accion(
  z.object({ capital: montoSchema, confirmo: z.literal("si", { message: "Confirmá que querés empezar de cero." }) }),
  async ({ capital }) => {
    await encolarComando("reiniciar_practica", { capital: Math.round(capital) });
    refrescar();
    return ok(`Anotado: la práctica arranca de cero con ${plata(capital)} en la próxima revisión.`);
  },
);

export const corregirAportado = accion(z.object({ total: montoSchema }), async ({ total }) => {
  const modo = modoDe(await leerPreferencias());
  const previo = await leerClaveEstado("aportes");
  const base = previo && typeof previo === "object" ? (previo as Record<string, Record<string, unknown>>) : {};
  const nuevo = { ...base, [modo]: { ...(base[modo] ?? {}), total: Math.round(total) } };
  await guardarEstado("aportes", nuevo);
  await registrarEvento("ajuste_aportes", { total: Math.round(total) }, modo);
  refrescar();
  return ok(`Corregido: el total que pusiste queda en ${plata(total)}.`);
});

const activarSchema = z.object({
  entiendo: z.literal("si", { message: "Tenés que marcar que lo entendés." }),
  palabra: z.string().trim().refine((s) => s === "ACTIVAR", { message: "Escribí ACTIVAR en mayúsculas." }),
});

export const activarReal = accion(activarSchema, async () => {
  const s = await secretosCargados();
  if (!s.IOL_USERNAME || !s.IOL_PASSWORD) return falla("Primero conectá tu cuenta de IOL (más arriba).");
  const desde = new Date().toISOString();
  await guardarPreferencias({ operador: { modo: "live" } });
  await guardarEstado("modo_real", { habilitado: true, desde });
  await registrarEvento("modo_real", { habilitado: true, desde }, "live");
  refrescar();
  return ok("Modo real activado. Desde la próxima revisión el operador maneja tu cuenta de IOL.");
});

export const volverPractica = accion(nada, async () => {
  await guardarPreferencias({ operador: { modo: "paper" } });
  await guardarEstado("modo_real", { habilitado: false, desde: null });
  await registrarEvento("modo_real", { habilitado: false }, "paper");
  refrescar();
  return ok("Volviste a modo práctica. El operador ya no toca tu cuenta real.");
});
