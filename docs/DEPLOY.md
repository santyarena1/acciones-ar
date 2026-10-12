# Puesta en marcha en la nube

Cómo queda armado:

- **Web** (Vercel, Next.js, carpeta `web/`): login, configuración, claves, botón "Revisar ahora".
- **Motor** (Python, GitHub Actions): analiza y opera cada hora con el mercado abierto.
- **Base** (Postgres en Neon): lo único que comparten la web y el motor. Nada vive en la PC.

El motor necesita solo dos secretos en GitHub: `DATABASE_URL` y `CLAVE_CIFRADO`. Las claves de IOL y de Telegram
se cargan desde la web y quedan **cifradas** en la base.

---

## 1. Crear la base (Neon desde Vercel)

1. En Vercel, en el proyecto de la web: **Storage → Create Database → Neon (Marketplace)**. Elegí la región más
   cercana (por ejemplo `aws-us-east-1` o São Paulo si está disponible).
2. Al conectarla al proyecto, Vercel crea las variables `DATABASE_URL` (y otras de Neon) en el proyecto.
3. Copiá el valor de `DATABASE_URL` (Vercel → Settings → Environment Variables, o la consola de Neon →
   *Connection string*). Tiene que terminar con `?sslmode=require`. Sirve tal cual: el motor la adapta solo
   (`postgres://` o `postgresql://`).
   - Usá la conexión **directa** o la *pooled*: las dos funcionan (el candado del motor es una fila, no un
     advisory lock).

## 2. Generar la clave de cifrado

Una sola clave para la web y el motor (32 bytes en base64). En cualquier terminal:

```bash
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
# o:  openssl rand -base64 32
```

Guardala en un gestor de contraseñas: si se pierde, hay que volver a cargar las claves de IOL y Telegram.

- En Vercel: variable `CLAVE_CIFRADO` (Production y Preview) con ese valor.
- En GitHub: secret `CLAVE_CIFRADO` (paso 3).

Compatibilidad web ↔ motor: AES-256-GCM, valor = `"v1:" + base64(nonce[12] || ciphertext || tag[16])`. El vector
de prueba está en `db/vector_cifrado.json` (la web tiene que reproducir el mismo `valor`).

## 3. Cargar los secrets en GitHub

Con la [CLI de GitHub](https://cli.github.com/) logueada, desde la carpeta del repo:

```bash
gh secret set DATABASE_URL      # pega la URL de Neon cuando la pida (no queda en el historial)
gh secret set CLAVE_CIFRADO     # pega la clave del paso 2
gh secret list                  # tienen que figurar los dos
```

No hace falta ningún otro secret (ni IOL ni Telegram): esos los lee el motor de la base.

## 4. Habilitar GitHub Actions

1. GitHub → repo → **Actions**: si aparece "Workflows aren't being run on this repository", habilitarlos.
2. Hay dos workflows:
   - **Tests** (`tests.yml`): corre en cada push y pull request.
   - **Operador** (`operador.yml`): cada hora a las :30 de 11:30 a 16:30 hora Argentina, lunes a viernes
     (feriados y horario se chequean adentro), y a mano con **Run workflow**.
3. Ojo: GitHub pausa los workflows programados de un repo público después de 60 días sin commits. Si pasa, se
   reactivan desde la pestaña Actions (o con cualquier commit).

## 5. Primera corrida (crea las tablas)

Actions → **Operador** → **Run workflow** → tildá `forzar` → Run.

El primer paso es `python main.py db-init`: aplica `db/schema.sql` (es idempotente, se corre en cada pasada; si
la web ya creó las tablas no cambia nada). Después corre el operador en **modo práctica** (por defecto).

Lo que se ve en el log es a propósito genérico (el repo es público):

```
[ok] esquema aplicado (13 sentencias)
[ok] claves cargadas: 0
[ok] corrida guardada; 12 órdenes
```

El detalle (órdenes, montos, errores) queda en la tabla `eventos` y se ve en la web.

Para probar desde la PC contra la misma base (opcional):

```bash
DATABASE_URL="postgresql://...?...sslmode=require" .venv/Scripts/python main.py db-init
```

## 6. Desde la web

- **Claves**: el dueño carga usuario/clave de IOL y token/chat de Telegram; la web las guarda cifradas en
  `secretos`. El motor las descifra en cada corrida (nunca las imprime).
- **Revisar ahora**: la web dispara el workflow (`workflow_dispatch` con `forzar=true`) y/o deja un pedido
  `revisar` en `comandos`. Con el mercado cerrado, en modo real la corrida **solo analiza** (nunca manda órdenes).
- **Depositar / reiniciar práctica**: la web inserta en `comandos` (`depositar_practica {monto}`,
  `reiniciar_practica {capital}`); el motor los procesa al empezar la próxima corrida.
- **Resumen diario por Telegram**: sale una vez por día hábil en la última corrida (~16:30).

## 7. Modo real (lo activa el dueño, nunca Claude)

Hacen falta **las dos cosas**, las dos desde la web con sesión iniciada:

1. Preferencias: `operador.modo = "live"` (tabla `preferencias`, clave `usuario`).
2. Habilitación: estado `modo_real = {"habilitado": true, "desde": "<fecha>"}` (tabla `estado`).

Si falta cualquiera de las dos, el motor no crea la conexión con IOL y registra el motivo. Para volver a práctica
alcanza con desactivar cualquiera de las dos. Todas las protecciones técnicas siguen activas en la nube (sin
órdenes repetidas, precio en vivo dentro de tolerancia, compras ≤ caja, tope por orden, candado, feriados).

## 8. Dejar de usar la PC

- Si estaba instalada la tarea programada de Windows, quitarla (si no, habría dos operadores):
  `Unregister-ScheduledTask -TaskName "AccionesAR - operador" -Confirm:$false`
- `scripts/*.ps1` y la app Streamlit (`app/`) quedan como legado para uso local, sin `DATABASE_URL`.
