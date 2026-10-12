import { mkdirSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

/**
 * Recorrido principal: primera vez (/setup) o ingreso -> inicio -> cada pantalla. Guarda capturas en
 * e2e/screenshots/<proyecto>/ (no se suben al repo).
 */
const EMAIL = process.env.E2E_EMAIL ?? "dueno@operador.test";
const CLAVE = process.env.E2E_PASSWORD ?? "clave-de-prueba-local";
const SETUP = process.env.SETUP_TOKEN ?? "";

async function entrar(page: Page) {
  await page.goto("/");
  await page.waitForURL(/\/(login|setup)|\/$/);
  if (page.url().includes("/setup")) {
    await page.getByLabel("Código de instalación").fill(SETUP);
    await page.getByLabel("Tu email").fill(EMAIL);
    await page.getByLabel("Contraseña nueva").fill(CLAVE);
    await page.getByLabel("Repetí la contraseña").fill(CLAVE);
    await page.getByRole("button", { name: "Crear acceso y entrar" }).click();
  } else if (page.url().includes("/login")) {
    await page.getByLabel("Email").fill(EMAIL);
    await page.getByLabel("Contraseña").fill(CLAVE);
    await page.getByRole("button", { name: "Entrar" }).click();
  }
  await page.waitForURL((u) => u.pathname === "/");
}

async function captura(page: Page, nombre: string, proyecto: string, oscuro = false) {
  const dir = `e2e/screenshots/${proyecto}`;
  mkdirSync(dir, { recursive: true });
  if (oscuro) await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  else await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${dir}/${nombre}${oscuro ? "-oscuro" : ""}.png`, fullPage: true });
}

test("la pantalla de ingreso no deja pasar sin sesión", async ({ page }) => {
  const r = await page.goto("/cartera");
  expect(r?.status()).toBeLessThan(400);
  await expect(page).toHaveURL(/\/(login|setup)/);
});

test("ingreso -> inicio y recorrido por las pantallas", async ({ page }, info) => {
  await entrar(page);
  await expect(page.getByText("Tu cartera vale")).toBeVisible();
  await captura(page, "01-inicio", info.project.name);
  await captura(page, "01-inicio", info.project.name, true);

  for (const [ruta, nombre, texto] of [
    ["/cartera", "02-cartera", "Lo que tenés"],
    ["/oportunidades", "03-oportunidades", "Lo que mira el operador"],
    ["/bonos", "04-bonos", "Renta fija"],
    ["/historial", "05-historial", "Todo lo que hizo"],
    ["/activo/YPFD", "06-activo", "YPF"],
    ["/configuracion", "07-configuracion", "Cómo trabaja tu operador"],
  ] as const) {
    await page.goto(ruta);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(texto);
    await captura(page, nombre, info.project.name);
  }
  await page.goto("/cartera");
  await captura(page, "02-cartera", info.project.name, true);
});

test("headers de seguridad presentes", async ({ request }) => {
  const r = await request.get("/login");
  const h = r.headers();
  expect(h["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(h["x-frame-options"]).toBe("DENY");
  expect(h["x-content-type-options"]).toBe("nosniff");
});

test("el webhook de Telegram rechaza pedidos sin secreto", async ({ request }) => {
  const r = await request.post("/api/telegram", { data: { message: { chat: { id: 1 }, text: "/estado" } } });
  expect(r.status()).toBe(401);
});
