import "server-only";
import { z } from "zod";

/**
 * Prueba de conexión con IOL: token (password grant) + estado de cuenta.
 * Nunca devuelve ni loguea el usuario, la contraseña o el token.
 */
const BASE = "https://api.invertironline.com";
const TIMEOUT_MS = 15_000;

export type ResultadoIol =
  | { ok: true; totalPesos: number | null; disponiblePesos: number | null }
  | { ok: false; motivo: string };

const tokenSchema = z.object({ access_token: z.string().min(10) });
const cuentaSchema = z.looseObject({
  totalEnPesos: z.number().nullable().optional(),
  cuentas: z
    .array(z.looseObject({ moneda: z.string().optional(), disponible: z.number().nullable().optional() }))
    .optional(),
});

export async function probarIol(usuario: string, clave: string, f: typeof fetch = fetch): Promise<ResultadoIol> {
  try {
    const r = await f(`${BASE}/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ grant_type: "password", username: usuario, password: clave }).toString(),
      signal: AbortSignal.timeout(TIMEOUT_MS),
      cache: "no-store",
    });
    if (r.status === 400 || r.status === 401) {
      return { ok: false, motivo: "IOL rechazó el usuario o la contraseña. Revisalos (son los mismos con los que entrás a la web de IOL)." };
    }
    if (!r.ok) return { ok: false, motivo: `IOL no respondió bien (código ${r.status}). Probá de nuevo en unos minutos.` };
    const tok = tokenSchema.safeParse(await r.json());
    if (!tok.success) return { ok: false, motivo: "IOL respondió algo inesperado al pedir acceso." };
    const c = await f(`${BASE}/api/v2/estadocuenta`, {
      headers: { Authorization: `Bearer ${tok.data.access_token}` },
      signal: AbortSignal.timeout(TIMEOUT_MS),
      cache: "no-store",
    });
    if (c.status === 401 || c.status === 403) {
      return {
        ok: false,
        motivo: "Entró, pero tu cuenta todavía no tiene habilitada la API. Pedí el alta en IOL (te explicamos cómo abajo).",
      };
    }
    if (!c.ok) return { ok: false, motivo: `Entró, pero no pude leer tu estado de cuenta (código ${c.status}).` };
    const cuenta = cuentaSchema.safeParse(await c.json());
    if (!cuenta.success) return { ok: true, totalPesos: null, disponiblePesos: null };
    const pesos = cuenta.data.cuentas?.find((x) => (x.moneda ?? "").toLowerCase().includes("peso"));
    return { ok: true, totalPesos: cuenta.data.totalEnPesos ?? null, disponiblePesos: pesos?.disponible ?? null };
  } catch (e) {
    const timeout = e instanceof Error && (e.name === "TimeoutError" || e.name === "AbortError");
    return {
      ok: false,
      motivo: timeout ? "IOL tardó demasiado en responder. Probá de nuevo." : "No pude comunicarme con IOL. Probá de nuevo en unos minutos.",
    };
  }
}
