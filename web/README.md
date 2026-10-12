# Operador — app web

La app con la que el dueño ve y controla el operador automático, sobre todo desde el teléfono. Next.js 15 (App
Router) + TypeScript estricto + Tailwind v4 + Drizzle. Se publica en **Vercel** con *Root Directory* = `web/`.

La web no calcula nada de inversiones: **lee** lo que escribe el motor en Python (corridas, bitácora, estado, cartera
de práctica) y **escribe** solo preferencias, pausa, modo real, secretos cifrados, pedidos (`comandos`) y el usuario.
El contrato es `../db/schema.sql`.

## Pantallas

| Ruta | Qué muestra |
|---|---|
| `/` Inicio | Valor total, lo que pusiste, ganancia real, contra "no hacer nada" (curva), reparto hoy vs. objetivo, últimos movimientos, qué está pensando |
| `/cartera` | Lo que tenés, agrupado por clase, con ganancia, peso y por qué lo tiene |
| `/oportunidades` | Mejores ideas (CEDEARs con señal de compra) + tabla completa con búsqueda, filtros y orden |
| `/bonos` | Bonos y letras por clase: rendimiento anual, plazo, vencimiento, barato/caro, nota + gráfico rendimiento vs. plazo |
| `/historial` | Todo lo que hizo el operador, agrupado por día |
| `/activo/[ticker]` | Ficha: nota, por qué, números, analistas y noticias del reporte semanal |
| `/configuracion` | Revisar ahora, pausar, perfil, plata, cuenta de IOL, práctica/real, Telegram |
| `/login`, `/setup` | Ingreso y alta del dueño (una sola vez) |
| `/api/telegram` | Webhook del bot (/estado, /cartera, /hoy, /pausar, /reanudar, /revisar, /ayuda) |

## Variables de entorno

| Variable | Obligatoria | Para qué |
|---|---|---|
| `DATABASE_URL` | Sí (en Vercel) | Postgres de Neon. En desarrollo se ignora salvo `USAR_DATABASE_URL_EN_DEV=1`: se usa PGlite local |
| `SESSION_SECRET` | Sí | Firma de la cookie de sesión (≥ 32 caracteres al azar: `openssl rand -base64 48`) |
| `SETUP_TOKEN` | Sí, para el primer ingreso | Código para crear la cuenta del dueño en `/setup` (≥ 24 caracteres). Después se puede borrar |
| `CLAVE_CIFRADO` | Sí | 32 bytes en base64, **la misma que usa el motor en GitHub Actions** (`openssl rand -base64 32`) |
| `TELEGRAM_WEBHOOK_SECRET` | Para los comandos del bot | Secreto que Telegram manda en cada mensaje (letras, números, `_` o `-`, 16 a 256) |
| `GITHUB_DISPATCH_TOKEN` | Opcional | Token *fine-grained* con permiso **Actions: write** sobre el repo: "Revisar ahora" arranca el operador al instante |
| `GITHUB_REPO` | Opcional | `santyarena1/acciones-ar` |
| `GITHUB_REF_OPERADOR` | Opcional | Rama del workflow (por defecto `master`) |
| `APP_URL` | Opcional | URL pública (para registrar el webhook de Telegram); si falta se toma del pedido |

Ver `.env.example`. Nunca subas valores reales.

## Desarrollo local (sin servidor de base de datos)

```bash
cd web
pnpm install
cp .env.example .env.local      # completá SESSION_SECRET, SETUP_TOKEN y CLAVE_CIFRADO con valores de prueba
pnpm seed                       # carga la última data REAL local del motor en web/.pglite (ver abajo)
pnpm dev                        # http://localhost:3000 -> te manda a /setup la primera vez
```

- La base local es **PGlite** (Postgres en WASM) en `web/.pglite`, con el mismo `../db/schema.sql`.
- `pnpm seed` lee en el momento (no se copia nada al repo) `../reports/corridas/*`, `../data/operador/bitacora.jsonl`,
  `../data/operador/estado.json`, `../data/paper_state.json` y `../data/usuario.yaml`.
  - `pnpm seed --reset` vacía todo (menos el usuario) y vuelve a cargar.
  - `pnpm seed --historia-demo` además inventa 45 días de "fotos" (marcadas `demo: true`) para ver la curva.
  - **Cerrá `pnpm dev` antes de correrlo**: PGlite no admite dos procesos sobre la misma carpeta.
- Next.js solo lee `.env*` de `web/` (nunca de carpetas de arriba). Y fuera de producción la app ignora
  `DATABASE_URL`, así que el desarrollo no puede tocar una base real por accidente.

## Pruebas

```bash
pnpm lint && pnpm typecheck
pnpm test                       # Vitest: formatos, etiquetas, razones, cifrado (vector del motor), auth, zod, datos (PGlite en memoria)
pnpm build && pnpm test:e2e     # Playwright: setup/login -> todas las pantallas a 375 px y 1440 px, en claro y oscuro
```

El e2e levanta `next start` con su propia base (`.pglite-e2e`, cargada con `pnpm seed --reset --historia-demo`) y
guarda capturas en `e2e/screenshots/` (no se suben). Usa `E2E_EMAIL`/`E2E_PASSWORD` de `.env.local` como cuenta de
prueba. Si el Chromium de Playwright no está bajado, usa uno instalado (`PW_CHROMIUM=ruta/a/chrome.exe`).

## Publicar en Vercel

1. Importar el repo en Vercel → **Root Directory: `web`** (framework Next.js, se detecta solo; comando de build por
   defecto `pnpm build`).
2. Cargar las variables de arriba en *Settings → Environment Variables* (Production).
3. Que el motor haya aplicado el esquema (`main.py db-init`) en la misma base de Neon.
4. Entrar a `https://<tu-app>/setup` con el `SETUP_TOKEN` y crear el acceso del dueño.
5. Configuración → Telegram → "Activar comandos" registra el webhook en `https://<tu-app>/api/telegram`.

## Seguridad (resumen)

- Sesión: cookie `HttpOnly; Secure; SameSite=Lax` firmada (HS256, 30 días). El middleware protege todo salvo
  `/login`, `/setup` y `/api/telegram`; cada acción del servidor vuelve a verificar la sesión.
- Contraseña con bcrypt (costo 12, mínimo 10 caracteres). Límite de intentos: 5 por IP y 30 en total cada 15 minutos
  (se registran como eventos `login_fallido`, con la IP hasheada).
- CSP con nonce por pedido (middleware) + HSTS, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`,
  `Permissions-Policy` (next.config.ts). CSRF: las Server Actions validan el origen.
- Secretos de IOL y Telegram cifrados con AES-256-GCM, compatibles byte a byte con el motor
  (`../db/vector_cifrado.json` se verifica en los tests). Nunca se devuelven al navegador ni se loguean.
- La prueba de IOL se hace del lado del servidor y solo se guarda si funciona.
- Telegram: solo se vincula el chat que le manda al bot un código derivado del token (el usuario del bot es público).
  El webhook verifica el secreto y responde solo a ese chat. La URL del webhook sale de `APP_URL` o del dominio de
  producción de Vercel, nunca de headers del pedido.
- Cada página lee los datos a través de `contextoApp()`, que vuelve a exigir sesión (no depende solo del layout).
- Pendiente conocido: la sesión es un token firmado sin revocación del lado del servidor (cerrar sesión borra la
  cookie de ese navegador). Si se sospecha de una cookie robada, rotar `SESSION_SECRET` invalida todas.

## Decisiones

- **Server Components** para todo lo que se lee; JS en el cliente solo en gráficos (hover), la tabla filtrable y los
  formularios.
- **Neon por HTTP** en producción (sin conexiones persistentes: ideal para funciones). **PGlite** en desarrollo y
  tests, con el mismo SQL. Drizzle tipa ambos.
- **visx** para los gráficos: piezas chicas (escalas y formas) sobre SVG propio, con el estilo del sistema de diseño.
- Diseño: "libro mayor de banca privada" — Instrument Serif para cifras y títulos, Geist para la interfaz, Geist Mono
  para símbolos; papel y tinta en claro, bóveda nocturna en oscuro; un único acento latón y verde/rojo solo para
  ganancia/pérdida (siempre con signo, nunca solo color). Colores por clase validados para daltonismo.
