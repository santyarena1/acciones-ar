"""Base de datos (Postgres en Neon) compartida entre el motor y la web. SQLAlchemy Core, sin ORM.

- Se activa con la variable de entorno `DATABASE_URL`. Sin ella, todo sigue en archivos locales (desarrollo).
- El contrato es `db/schema.sql` (solo Postgres; lo aplica `python main.py db-init`). Las tablas de abajo son
  el equivalente portable para los tests con SQLite: si cambia el esquema, cambian los dos.
- Fechas: se escriben siempre en UTC con zona; al leer, una fecha sin zona (SQLite) se toma como UTC.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import Engine

ENV_URL = "DATABASE_URL"
SCHEMA_SQL = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
_TS = sa.DateTime(timezone=True)

metadata = sa.MetaData()


def _kv(nombre: str) -> sa.Table:
    return sa.Table(nombre, metadata, sa.Column("clave", sa.Text, primary_key=True),
                    sa.Column("valor", _JSON, nullable=False),
                    sa.Column("actualizado", _TS, nullable=False, server_default=sa.func.now()))


usuarios = sa.Table("usuarios", metadata, sa.Column("email", sa.Text, primary_key=True),   # lo maneja la web
                    sa.Column("hash", sa.Text, nullable=False),
                    sa.Column("creado", _TS, nullable=False, server_default=sa.func.now()))
secretos = sa.Table("secretos", metadata, sa.Column("clave", sa.Text, primary_key=True),
                    sa.Column("valor", sa.Text, nullable=False),
                    sa.Column("actualizado", _TS, nullable=False, server_default=sa.func.now()))
preferencias = _kv("preferencias")
estado = _kv("estado")
paper = _kv("paper")
eventos = sa.Table("eventos", metadata, sa.Column("id", _ID, primary_key=True, autoincrement=True),
                   sa.Column("ts", _TS, nullable=False, server_default=sa.func.now()),
                   sa.Column("modo", sa.Text), sa.Column("tipo", sa.Text, nullable=False),
                   sa.Column("datos", _JSON, nullable=False))
corridas = sa.Table("corridas", metadata, sa.Column("stamp", sa.Text, primary_key=True),
                    sa.Column("creada", _TS, nullable=False, server_default=sa.func.now()),
                    sa.Column("modo", sa.Text, nullable=False), sa.Column("meta", _JSON, nullable=False),
                    sa.Column("ranking", _JSON, nullable=False), sa.Column("renta_fija", _JSON, nullable=False),
                    sa.Column("objetivos", _JSON, nullable=False), sa.Column("ordenes", _JSON, nullable=False),
                    sa.Column("guia", sa.Text, nullable=False))
reportes = sa.Table("reportes", metadata, sa.Column("numero", sa.Integer, primary_key=True),
                    sa.Column("fecha", sa.Date), sa.Column("datos", _JSON, nullable=False))
comandos = sa.Table("comandos", metadata, sa.Column("id", _ID, primary_key=True, autoincrement=True),
                    sa.Column("ts", _TS, nullable=False, server_default=sa.func.now()),
                    sa.Column("tipo", sa.Text, nullable=False), sa.Column("datos", _JSON, nullable=False),
                    sa.Column("procesado", _TS), sa.Column("resultado", _JSON))
TABLAS_KV = {"preferencias": preferencias, "estado": estado, "paper": paper}

_MOTORES: dict[str, Engine] = {}


# ----------------------------------------------------------------------------- conexión
def hay_db() -> bool:
    return bool(os.getenv(ENV_URL, "").strip())


def normalizar_url(url: str) -> str:
    """Neon/Vercel entregan `postgres://` o `postgresql://`: se fuerza el driver psycopg 3."""
    url = url.strip()
    for prefijo in ("postgres://", "postgresql://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg://" + url[len(prefijo):]
    return url


def _json_dumps(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, default=str)


def motor(url: str | None = None) -> Engine:
    """Engine cacheado por URL. Nunca se loguea la URL (lleva la contraseña)."""
    crudo = url or os.getenv(ENV_URL, "")
    if not crudo.strip():
        raise RuntimeError("Falta DATABASE_URL.")
    u = normalizar_url(crudo)
    if u not in _MOTORES:
        _MOTORES[u] = sa.create_engine(u, pool_pre_ping=True, json_serializer=_json_dumps, hide_parameters=True)
    return _MOTORES[u]


def crear_tablas(engine: Engine | None = None) -> None:
    """Crea las tablas con el equivalente portable (tests con SQLite)."""
    metadata.create_all(engine or motor())


def sentencias_schema(sql: str) -> list[str]:
    """Parte schema.sql en sentencias (sin comentarios). El esquema no usa funciones ni `$$`."""
    sin_comentarios = "\n".join(re.sub(r"--.*$", "", linea) for linea in sql.splitlines())
    return [s.strip() for s in sin_comentarios.split(";") if s.strip()]


def aplicar_esquema(engine: Engine | None = None) -> int:
    """`db-init`: en Postgres aplica db/schema.sql (idempotente); en otro motor, las tablas portables."""
    eng = engine or motor()
    if eng.dialect.name != "postgresql":
        crear_tablas(eng)
        return len(metadata.tables)
    sentencias = sentencias_schema(SCHEMA_SQL.read_text(encoding="utf-8"))
    with eng.begin() as conn:
        for s in sentencias:
            conn.exec_driver_sql(s)
    return len(sentencias)


# ----------------------------------------------------------------------------- utilidades
def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def a_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _upsert(conn, tabla: sa.Table, fila: dict, clave: str) -> None:
    dialecto = postgresql if conn.dialect.name == "postgresql" else sqlite
    stmt = dialecto.insert(tabla).values(**fila)
    cambios = {k: stmt.excluded[k] for k in fila if k != clave}
    conn.execute(stmt.on_conflict_do_update(index_elements=[clave], set_=cambios))


def _insert_si_no_existe(conn, tabla: sa.Table, fila: dict, clave: str) -> bool:
    dialecto = postgresql if conn.dialect.name == "postgresql" else sqlite
    stmt = dialecto.insert(tabla).values(**fila).on_conflict_do_nothing(index_elements=[clave])
    return conn.execute(stmt.returning(tabla.c[clave])).first() is not None   # rowcount no es confiable acá


# ----------------------------------------------------------------------------- clave/valor (jsonb)
def kv_get(tabla: str, clave: str, defecto: Any = None, engine: Engine | None = None) -> Any:
    t = TABLAS_KV[tabla]
    with (engine or motor()).connect() as conn:
        fila = conn.execute(sa.select(t.c.valor).where(t.c.clave == clave)).first()
    return defecto if fila is None else fila[0]


def kv_todos(tabla: str, engine: Engine | None = None) -> dict[str, Any]:
    t = TABLAS_KV[tabla]
    with (engine or motor()).connect() as conn:
        return {k: v for k, v in conn.execute(sa.select(t.c.clave, t.c.valor))}


def kv_set(tabla: str, clave: str, valor: Any, engine: Engine | None = None) -> None:
    kv_set_varios(tabla, {clave: valor}, engine)


def kv_set_varios(tabla: str, valores: dict[str, Any], engine: Engine | None = None) -> None:
    """Upsert de varias claves en una sola transacción (todo o nada)."""
    t, ts = TABLAS_KV[tabla], ahora_utc()
    with (engine or motor()).begin() as conn:
        for clave, valor in valores.items():
            _upsert(conn, t, {"clave": clave, "valor": valor, "actualizado": ts}, "clave")


def kv_borrar(tabla: str, clave: str, engine: Engine | None = None) -> None:
    t = TABLAS_KV[tabla]
    with (engine or motor()).begin() as conn:
        conn.execute(sa.delete(t).where(t.c.clave == clave))


# ----------------------------------------------------------------------------- candado (fila en estado)
def tomar_candado(info: dict, vence_seg: float, engine: Engine | None = None) -> tuple[datetime | None, bool]:
    """Toma la fila estado['candado'] de forma atómica. Devuelve (marca, reemplazó_uno_abandonado);
    marca=None si otra corrida lo tiene. Un candado más viejo que `vence_seg` se reemplaza (UPDATE ... WHERE)."""
    marca = ahora_utc()
    fila = {"clave": "candado", "valor": info, "actualizado": marca}
    with (engine or motor()).begin() as conn:
        if _insert_si_no_existe(conn, estado, fila, "clave"):
            return marca, False
        r = conn.execute(sa.update(estado)
                         .where(estado.c.clave == "candado", estado.c.actualizado < marca - timedelta(seconds=vence_seg))
                         .values(valor=info, actualizado=marca).returning(estado.c.clave)).first()
    return (marca, True) if r is not None else (None, False)


def soltar_candado(marca: datetime, engine: Engine | None = None) -> None:
    """Borra el candado solo si sigue siendo el nuestro (misma marca de tiempo)."""
    with (engine or motor()).begin() as conn:
        conn.execute(sa.delete(estado).where(estado.c.clave == "candado", estado.c.actualizado == marca))


# ----------------------------------------------------------------------------- eventos
def insertar_evento(tipo: str, modo: str | None, datos: dict, ts: datetime, engine: Engine | None = None) -> int:
    with (engine or motor()).begin() as conn:
        r = conn.execute(sa.insert(eventos).values(ts=a_utc(ts), modo=modo, tipo=tipo, datos=datos))
        return int(r.inserted_primary_key[0])


def consultar_eventos(tipos: Iterable[str] | None = None, desde: datetime | None = None,
                      ultimos: int | None = None, engine: Engine | None = None) -> list[dict]:
    """Filas {id, ts (UTC), modo, tipo, datos} en orden cronológico."""
    q = sa.select(eventos.c.id, eventos.c.ts, eventos.c.modo, eventos.c.tipo, eventos.c.datos)
    if tipos is not None:
        q = q.where(eventos.c.tipo.in_(list(tipos)))
    if desde is not None:
        q = q.where(eventos.c.ts >= a_utc(desde))
    q = q.order_by(eventos.c.id.desc() if ultimos else eventos.c.id)
    if ultimos:
        q = q.limit(int(ultimos))
    with (engine or motor()).connect() as conn:
        filas = [dict(f._mapping) for f in conn.execute(q)]
    filas = filas[::-1] if ultimos else filas
    return [{**f, "ts": a_utc(f["ts"])} for f in filas]


# ----------------------------------------------------------------------------- corridas
def guardar_corrida(fila: dict, engine: Engine | None = None) -> None:
    """fila: stamp, modo, meta, ranking, renta_fija, objetivos, ordenes, guia (listas/dicts ya limpios)."""
    with (engine or motor()).begin() as conn:
        _upsert(conn, corridas, {**fila, "creada": ahora_utc()}, "stamp")


def cargar_corrida(stamp: str, engine: Engine | None = None) -> dict | None:
    with (engine or motor()).connect() as conn:
        f = conn.execute(sa.select(corridas).where(corridas.c.stamp == stamp)).first()
    return dict(f._mapping) if f else None


def listar_corridas(limite: int | None = None, engine: Engine | None = None) -> list[str]:
    q = sa.select(corridas.c.stamp).order_by(corridas.c.stamp.desc())
    if limite:
        q = q.limit(int(limite))
    with (engine or motor()).connect() as conn:
        return [s for (s,) in conn.execute(q)]


# ----------------------------------------------------------------------------- reportes semanales
def numeros_reportes(engine: Engine | None = None) -> set[int]:
    with (engine or motor()).connect() as conn:
        return {int(n) for (n,) in conn.execute(sa.select(reportes.c.numero))}


def guardar_reporte(numero: int, fecha: date | None, datos: dict, engine: Engine | None = None) -> None:
    with (engine or motor()).begin() as conn:
        _upsert(conn, reportes, {"numero": int(numero), "fecha": fecha, "datos": datos}, "numero")


def cargar_reportes(engine: Engine | None = None) -> list[dict]:
    with (engine or motor()).connect() as conn:
        return [d for (d,) in conn.execute(sa.select(reportes.c.datos).order_by(reportes.c.numero))]


# ----------------------------------------------------------------------------- comandos de la web
def comandos_pendientes(engine: Engine | None = None) -> list[dict]:
    q = (sa.select(comandos.c.id, comandos.c.ts, comandos.c.tipo, comandos.c.datos)
         .where(comandos.c.procesado.is_(None)).order_by(comandos.c.id))
    with (engine or motor()).connect() as conn:
        return [dict(f._mapping) for f in conn.execute(q)]


def reclamar_comando(id_: int, engine: Engine | None = None) -> bool:
    """Marca el pedido como procesado ANTES de ejecutarlo (a lo sumo una vez: si la corrida muere a mitad de
    camino no se repite un depósito). False si otra corrida ya lo tomó."""
    with (engine or motor()).begin() as conn:
        r = conn.execute(sa.update(comandos).where(comandos.c.id == id_, comandos.c.procesado.is_(None))
                         .values(procesado=ahora_utc(), resultado={"ok": None, "estado": "procesando"})
                         .returning(comandos.c.id)).first()
    return r is not None


def resultado_comando(id_: int, resultado: dict, engine: Engine | None = None) -> None:
    with (engine or motor()).begin() as conn:
        conn.execute(sa.update(comandos).where(comandos.c.id == id_).values(resultado=resultado))


def leer_comando(id_: int, engine: Engine | None = None) -> dict | None:
    with (engine or motor()).connect() as conn:
        f = conn.execute(sa.select(comandos).where(comandos.c.id == id_)).first()
    return dict(f._mapping) if f else None


def encolar_comando(tipo: str, datos: dict | None = None, engine: Engine | None = None) -> int:
    """Lo usa la web (y los tests): deja un pedido para la próxima corrida del operador."""
    with (engine or motor()).begin() as conn:
        r = conn.execute(sa.insert(comandos).values(ts=ahora_utc(), tipo=tipo, datos=datos or {}))
        return int(r.inserted_primary_key[0])
