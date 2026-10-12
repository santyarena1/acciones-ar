import "server-only";
import { cache } from "react";
import { exigirSesion } from "../auth/sesion";
import type { Corrida } from "../domain/corrida";
import type { EstadoOperador } from "../domain/estado";
import type { Modo } from "../domain/schemas";
import type { PerfilId } from "../perfiles";
import { ultimaCorrida } from "./corridas";
import { leerEstado } from "./estado";
import { ultimaRevision } from "./eventos";
import { leerPreferencias, modoDe, perfilDe, type Preferencias } from "./preferencias";

export interface ContextoApp {
  preferencias: Preferencias;
  modo: Modo;
  perfil: PerfilId;
  estado: EstadoOperador;
  corrida: Corrida | null;
  ultimaRevision: string | null;
}

/**
 * Datos del operador sin control de sesión: solo para rutas que se autentican por su cuenta (webhook de Telegram).
 */
export const contextoDatos = cache(async (): Promise<ContextoApp> => {
  const preferencias = await leerPreferencias();
  const modo = modoDe(preferencias);
  const [estado, corrida, revision] = await Promise.all([leerEstado(), ultimaCorrida(modo), ultimaRevision()]);
  return { preferencias, modo, perfil: perfilDe(preferencias), estado, corrida, ultimaRevision: revision };
});

/**
 * Lo que casi todas las pantallas necesitan, una sola vez por pedido. Exige sesión: es la capa de acceso a datos de
 * las páginas (el layout no es una barrera confiable porque layout y página se renderizan en paralelo).
 */
export const contextoApp = cache(async (): Promise<ContextoApp> => {
  await exigirSesion();
  return contextoDatos();
});
