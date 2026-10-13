import "server-only";

import { after } from "next/server";

/**
 * "Revisar ahora": pide al motor un ciclo inmediato.
 *
 * 1. Si hay MOTOR_URL + MOTOR_SECRET: llama directo a la función del motor en Vercel
 *    (proyecto acciones-ar-motor, `/api/operar?forzar=1`). La corrida tarda ~1 minuto, así que se dispara con
 *    `after()` (sigue después de responder al usuario) y la pantalla no queda esperando.
 * 2. Si no, y hay GITHUB_DISPATCH_TOKEN + GITHUB_REPO: dispara el workflow de respaldo en GitHub Actions.
 * 3. Si no hay nada configurado: el comando queda en cola para la próxima revisión programada.
 */
export type ResultadoDispatch = "disparado" | "sin_configurar" | "fallo";

export async function dispararOperador(): Promise<ResultadoDispatch> {
  const motor = dispararMotorVercel();
  if (motor !== "sin_configurar") return motor;
  return dispararGithub();
}

function dispararMotorVercel(): ResultadoDispatch {
  const base = process.env.MOTOR_URL;
  const secreto = process.env.MOTOR_SECRET;
  if (!base || !secreto || !/^https:\/\/[\w.-]+$/.test(base.replace(/\/$/, ""))) return "sin_configurar";
  after(async () => {
    try {
      const r = await fetch(`${base.replace(/\/$/, "")}/api/operar?forzar=1`, {
        method: "POST",
        headers: { Authorization: `Bearer ${secreto}` },
        signal: AbortSignal.timeout(290_000),
        cache: "no-store",
      });
      if (!r.ok) console.error(`[revisar] el motor respondió ${r.status}`);
    } catch (e) {
      console.error("[revisar] no se pudo llamar al motor:", e instanceof Error ? e.name : "error");
    }
  });
  return "disparado";
}

async function dispararGithub(): Promise<ResultadoDispatch> {
  const token = process.env.GITHUB_DISPATCH_TOKEN;
  const repo = process.env.GITHUB_REPO;
  if (!token || !repo || !/^[\w.-]+\/[\w.-]+$/.test(repo)) return "sin_configurar";
  try {
    const r = await fetch(`https://api.github.com/repos/${repo}/actions/workflows/operador.yml/dispatches`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: process.env.GITHUB_REF_OPERADOR ?? "master", inputs: { forzar: true } }),
      signal: AbortSignal.timeout(10_000),
      cache: "no-store",
    });
    if (r.status === 204) return "disparado";
    console.error(`[revisar] GitHub respondió ${r.status} al disparar el operador`);
    return "fallo";
  } catch (e) {
    console.error("[revisar] no se pudo disparar el operador:", e instanceof Error ? e.name : "error");
    return "fallo";
  }
}
