import { NextResponse, type NextRequest } from "next/server";
import { COOKIE_SESION, verificarSesion } from "@/lib/auth/token";

/**
 * 1) CSP con nonce por pedido (Next lo aplica a sus scripts al ver el header en el request).
 * 2) Protege todo salvo /login, /setup y /api/telegram (el webhook se autentica con su propio secreto).
 */
const PUBLICAS = ["/login", "/setup", "/api/telegram"];

function csp(nonce: string): string {
  const dev = process.env.NODE_ENV !== "production";
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src 'self'${dev ? " ws:" : ""}`,
    "frame-ancestors 'none'",
    "form-action 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    ...(dev ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const nonce = btoa(crypto.randomUUID());
  const politica = csp(nonce);

  const publica = PUBLICAS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  if (!publica) {
    const email = await verificarSesion(req.cookies.get(COOKIE_SESION)?.value, process.env.SESSION_SECRET);
    if (!email) {
      const url = req.nextUrl.clone();
      url.pathname = "/login";
      url.search = pathname !== "/" ? `?volver=${encodeURIComponent(pathname)}` : "";
      const r = NextResponse.redirect(url);
      r.headers.set("Content-Security-Policy", politica);
      return r;
    }
  }

  const reqHeaders = new Headers(req.headers);
  reqHeaders.set("x-nonce", nonce);
  reqHeaders.set("Content-Security-Policy", politica);
  const res = NextResponse.next({ request: { headers: reqHeaders } });
  res.headers.set("Content-Security-Policy", politica);
  return res;
}

export const config = {
  matcher: [
    // sin excepciones por headers de prefetch: cualquiera podría mandarlos para saltarse el control
    "/((?!_next/static|_next/image|favicon.ico|icon.svg|apple-icon.png|manifest.webmanifest|robots.txt).*)",
  ],
};
