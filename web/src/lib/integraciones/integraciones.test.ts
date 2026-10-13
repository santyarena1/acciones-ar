import { afterEach, describe, expect, test, vi } from "vitest";
import { dispararOperador } from "./github";
import { probarIol } from "./iol";
import { buscarChat, codigoVinculo, enviarMensaje, registrarWebhook, tokenTelegramSchema } from "./telegram";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("probarIol", () => {
  test("token + estado de cuenta: devuelve saldos, nunca el token", async () => {
    const f = vi.fn().mockResolvedValueOnce(json(200, { access_token: "tok-1234567890" })).mockResolvedValueOnce(
      json(200, { totalEnPesos: 500000, cuentas: [{ moneda: "peso_Argentino", disponible: 120000 }] }),
    );
    const r = await probarIol("u", "p", f as unknown as typeof fetch);
    expect(r).toEqual({ ok: true, totalPesos: 500000, disponiblePesos: 120000 });
    expect(JSON.stringify(r)).not.toContain("tok-");
    const [url, init] = f.mock.calls[0]!;
    expect(url).toBe("https://api.invertironline.com/token");
    expect(String(init.body)).toBe("grant_type=password&username=u&password=p");
    expect(f.mock.calls[1]![1].headers.Authorization).toBe("Bearer tok-1234567890");
  });
  test("credenciales malas", async () => {
    const r = await probarIol("u", "p", vi.fn().mockResolvedValue(json(400, {})) as unknown as typeof fetch);
    expect(r).toMatchObject({ ok: false, motivo: expect.stringMatching(/rechazó/) });
  });
  test("API no habilitada", async () => {
    const f = vi.fn().mockResolvedValueOnce(json(200, { access_token: "tok-1234567890" })).mockResolvedValueOnce(json(401, {}));
    expect(await probarIol("u", "p", f as unknown as typeof fetch)).toMatchObject({ ok: false, motivo: expect.stringMatching(/API/) });
  });
  test("caída de red", async () => {
    const r = await probarIol("u", "p", vi.fn().mockRejectedValue(new TypeError("fetch failed")) as unknown as typeof fetch);
    expect(r).toMatchObject({ ok: false, motivo: expect.stringMatching(/No pude comunicarme/) });
  });
});

describe("dispararOperador", () => {
  test("sin configurar no llama a GitHub", async () => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    vi.stubEnv("GITHUB_DISPATCH_TOKEN", "");
    expect(await dispararOperador()).toBe("sin_configurar");
    expect(f).not.toHaveBeenCalled();
  });
  test("dispara workflow_dispatch con forzar=true en master", async () => {
    const f = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", f);
    vi.stubEnv("GITHUB_DISPATCH_TOKEN", "ghp_x");
    vi.stubEnv("GITHUB_REPO", "santyarena1/acciones-ar");
    expect(await dispararOperador()).toBe("disparado");
    const [url, init] = f.mock.calls[0]!;
    expect(url).toBe("https://api.github.com/repos/santyarena1/acciones-ar/actions/workflows/operador.yml/dispatches");
    expect(JSON.parse(init.body)).toEqual({ ref: "master", inputs: { forzar: true } });
  });
  test("respuesta de error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 404 })));
    vi.stubEnv("GITHUB_DISPATCH_TOKEN", "ghp_x");
    vi.stubEnv("GITHUB_REPO", "a/b");
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(await dispararOperador()).toBe("fallo");
  });
});

describe("telegram", () => {
  test("valida la forma del token", () => {
    expect(tokenTelegramSchema.safeParse("123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw").success).toBe(true);
    expect(tokenTelegramSchema.safeParse("hola").success).toBe(false);
  });
  test("código de vinculación: estable por token y secreto, distinto entre bots", () => {
    const a = codigoVinculo("tok-a", "secreto");
    expect(a).toMatch(/^[0-9A-F]{8}$/);
    expect(codigoVinculo("tok-a", "secreto")).toBe(a);
    expect(codigoVinculo("tok-b", "secreto")).not.toBe(a);
    expect(codigoVinculo("tok-a", "otro")).not.toBe(a);
  });
  test("buscarChat vincula solo el chat que mandó el código (no el último que escribió)", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(json(200, { ok: true, result: { id: 1 } }))
        .mockResolvedValueOnce(json(200, { ok: true, result: [{ message: { chat: { id: 42, type: "private", first_name: "Santy" }, text: "/start abcd1234" } }, { message: { chat: { id: 666, type: "private" }, text: "/start" } }] })),
    );
    expect(await buscarChat("t", "ABCD1234")).toEqual({ ok: true, chatId: "42", nombre: "Santy" });
  });
  test("buscarChat sin mensajes / token inválido", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json(200, { ok: true })).mockResolvedValueOnce(json(200, { ok: true, result: [] })));
    expect(await buscarChat("t", "ABCD1234")).toMatchObject({ ok: false, motivo: expect.stringMatching(/start ABCD1234/) });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(401, { ok: false })));
    expect(await buscarChat("t", "ABCD1234")).toMatchObject({ ok: false, motivo: expect.stringMatching(/token/) });
  });
  test("enviarMensaje y webhook", async () => {
    const f = vi.fn().mockImplementation(async () => json(200, { ok: true }));
    vi.stubGlobal("fetch", f);
    expect(await enviarMensaje("t", "42", "hola")).toBe(true);
    expect(JSON.parse(f.mock.calls[0]![1].body)).toMatchObject({ chat_id: "42", text: "hola", parse_mode: "HTML" });
    expect(await registrarWebhook("t", "https://x/api/telegram", "s".repeat(20))).toEqual({ ok: true });
    expect(JSON.parse(f.mock.calls[1]![1].body)).toMatchObject({ url: "https://x/api/telegram", secret_token: "s".repeat(20) });
  });
});

describe("dispararOperador con motor en Vercel", () => {
  test("llama al motor con el secreto, en segundo plano", async () => {
    vi.resetModules();
    const tareas: Array<() => Promise<void>> = [];
    vi.doMock("next/server", () => ({ after: (fn: () => Promise<void>) => tareas.push(fn) }));
    vi.stubEnv("MOTOR_URL", "https://motor.example.app");
    vi.stubEnv("MOTOR_SECRET", "secreto-del-motor");
    const llamadas: Array<[string, RequestInit]> = [];
    vi.stubGlobal("fetch", vi.fn(async (u: string, i: RequestInit) => {
      llamadas.push([u, i]);
      return new Response(null, { status: 200 });
    }));
    const { dispararOperador: disparar } = await import("./github");
    expect(await disparar()).toBe("disparado");
    expect(tareas).toHaveLength(1);
    await tareas[0]!();
    const [url, init] = llamadas[0]!;
    expect(url).toBe("https://motor.example.app/api/operar?forzar=1");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer secreto-del-motor");
    vi.doUnmock("next/server");
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });
});
