import "server-only";

/** Dispara el workflow del operador (`.github/workflows/operador.yml`) con forzar=true, si hay token. */
export type ResultadoDispatch = "disparado" | "sin_configurar" | "fallo";

export async function dispararOperador(): Promise<ResultadoDispatch> {
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
