-- Esquema de la base (Postgres / Neon). Contrato entre el motor (Python, corre en GitHub Actions) y la web
-- (Next.js en Vercel). Idempotente: se puede correr varias veces.
--
-- Modos: 'paper' (práctica) y 'live' (cuenta real de IOL). Todo lo que depende del modo lleva la columna `modo`.

-- Cuenta del dueño (un solo usuario). La web crea el usuario en el primer ingreso con SETUP_TOKEN.
CREATE TABLE IF NOT EXISTS usuarios (
  email        text PRIMARY KEY,
  hash         text NOT NULL,              -- bcrypt
  creado       timestamptz NOT NULL DEFAULT now()
);

-- Secretos cifrados con AES-256-GCM (clave CLAVE_CIFRADO, 32 bytes en base64, en Vercel y en GitHub Actions).
-- valor = 'v1:' || base64(nonce[12] || ciphertext || tag[16]). Claves: IOL_USERNAME, IOL_PASSWORD,
-- TELEGRAM_TOKEN, TELEGRAM_CHAT_ID.
CREATE TABLE IF NOT EXISTS secretos (
  clave        text PRIMARY KEY,
  valor        text NOT NULL,
  actualizado  timestamptz NOT NULL DEFAULT now()
);

-- Preferencias del dueño (pisan config/settings.yaml). Una sola fila: clave 'usuario', valor = dict anidado
-- (ej. {"operador": {"perfil": "moderado_agresivo", "modo": "paper"}}).
CREATE TABLE IF NOT EXISTS preferencias (
  clave        text PRIMARY KEY,
  valor        jsonb NOT NULL,
  actualizado  timestamptz NOT NULL DEFAULT now()
);

-- Estado del operador (clave/valor): 'pausado' {pausado, motivo}, 'modo_real' {habilitado, desde},
-- 'aportes' {paper:{total,caja,caja_ts}, live:{...}}, 'seguimiento' {paper:{...}, live:{...}},
-- 'ultimo_pedido_fondos' ({monto,texto,recompras} o null), 'ultimo_rebalanceo' (stamp), 'ultimo_resumen_diario'
-- ('AAAA-MM-DD'), 'candado' {pid, ts, corrida} (lo maneja el motor: la web no lo toca).
CREATE TABLE IF NOT EXISTS estado (
  clave        text PRIMARY KEY,
  valor        jsonb NOT NULL,
  actualizado  timestamptz NOT NULL DEFAULT now()
);

-- Bitácora: un evento por fila (nunca se borra). tipo: orden, intento_orden, corrida, aporte, foto, pedido_fondos,
-- descartada, error, pausa, reanudar, cancelacion, aviso_caida, modo_real, comando, aviso...
CREATE TABLE IF NOT EXISTS eventos (
  id           bigserial PRIMARY KEY,
  ts           timestamptz NOT NULL DEFAULT now(),
  modo         text,
  tipo         text NOT NULL,
  datos        jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS eventos_tipo_ts ON eventos (tipo, ts DESC);
CREATE INDEX IF NOT EXISTS eventos_ts ON eventos (ts DESC);

-- Cartera de práctica (broker paper). Una fila: clave 'cartera', valor = {caja, posiciones, historial}.
CREATE TABLE IF NOT EXISTS paper (
  clave        text PRIMARY KEY,
  valor        jsonb NOT NULL,
  actualizado  timestamptz NOT NULL DEFAULT now()
);

-- Corridas del análisis completo. Las tablas grandes van como jsonb (lista de filas, orient='records').
CREATE TABLE IF NOT EXISTS corridas (
  stamp        text PRIMARY KEY,           -- AAAAMMDD_HHMM
  creada       timestamptz NOT NULL DEFAULT now(),
  modo         text NOT NULL,
  meta         jsonb NOT NULL,             -- macro, asignacion, cartera, tactico, escala, reporte_semanal, contexto...
  ranking      jsonb NOT NULL,             -- [{ticker, tipo, sector, score, senal, ...}]
  renta_fija   jsonb NOT NULL DEFAULT '[]'::jsonb,
  objetivos    jsonb NOT NULL DEFAULT '[]'::jsonb,
  ordenes      jsonb NOT NULL DEFAULT '[]'::jsonb,
  guia         text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS corridas_creada ON corridas (creada DESC);

-- Reportes semanales de Gorostiaga ya parseados (solo los últimos 3 son públicos: el histórico vive acá).
CREATE TABLE IF NOT EXISTS reportes (
  numero       integer PRIMARY KEY,
  fecha        date,
  datos        jsonb NOT NULL
);

-- Pedidos de la web al motor (los procesa el operador al empezar cada corrida, en orden).
-- tipo: 'depositar_practica' {monto}, 'reiniciar_practica' {capital}, 'revisar' {}.
CREATE TABLE IF NOT EXISTS comandos (
  id           bigserial PRIMARY KEY,
  ts           timestamptz NOT NULL DEFAULT now(),
  tipo         text NOT NULL,
  datos        jsonb NOT NULL DEFAULT '{}'::jsonb,
  procesado    timestamptz,
  resultado    jsonb
);
CREATE INDEX IF NOT EXISTS comandos_pendientes ON comandos (procesado) WHERE procesado IS NULL;
