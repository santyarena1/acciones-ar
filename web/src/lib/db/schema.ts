/**
 * Espejo en Drizzle de `db/schema.sql` (contrato con el motor en Python). La fuente de verdad es el SQL:
 * `schema.test.ts` verifica que tablas y columnas coincidan.
 */
import { bigserial, date, index, integer, jsonb, pgTable, text, timestamp } from "drizzle-orm/pg-core";

const ts = (name: string) => timestamp(name, { withTimezone: true, mode: "string" });

export const usuarios = pgTable("usuarios", {
  email: text("email").primaryKey(),
  hash: text("hash").notNull(),
  creado: ts("creado").notNull().defaultNow(),
});

export const secretos = pgTable("secretos", {
  clave: text("clave").primaryKey(),
  valor: text("valor").notNull(),
  actualizado: ts("actualizado").notNull().defaultNow(),
});

export const preferencias = pgTable("preferencias", {
  clave: text("clave").primaryKey(),
  valor: jsonb("valor").$type<Record<string, unknown>>().notNull(),
  actualizado: ts("actualizado").notNull().defaultNow(),
});

export const estado = pgTable("estado", {
  clave: text("clave").primaryKey(),
  valor: jsonb("valor").$type<unknown>().notNull(),
  actualizado: ts("actualizado").notNull().defaultNow(),
});

export const eventos = pgTable(
  "eventos",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    ts: ts("ts").notNull().defaultNow(),
    modo: text("modo"),
    tipo: text("tipo").notNull(),
    datos: jsonb("datos").$type<Record<string, unknown>>().notNull().default({}),
  },
  (t) => [index("eventos_ts").on(t.ts)],
);

export const paper = pgTable("paper", {
  clave: text("clave").primaryKey(),
  valor: jsonb("valor").$type<unknown>().notNull(),
  actualizado: ts("actualizado").notNull().defaultNow(),
});

export const corridas = pgTable("corridas", {
  stamp: text("stamp").primaryKey(),
  creada: ts("creada").notNull().defaultNow(),
  modo: text("modo").notNull(),
  meta: jsonb("meta").$type<unknown>().notNull(),
  ranking: jsonb("ranking").$type<unknown>().notNull(),
  rentaFija: jsonb("renta_fija").$type<unknown>().notNull().default([]),
  objetivos: jsonb("objetivos").$type<unknown>().notNull().default([]),
  ordenes: jsonb("ordenes").$type<unknown>().notNull().default([]),
  guia: text("guia").notNull().default(""),
});

export const reportes = pgTable("reportes", {
  numero: integer("numero").primaryKey(),
  fecha: date("fecha", { mode: "string" }),
  datos: jsonb("datos").$type<unknown>().notNull(),
});

export const comandos = pgTable("comandos", {
  id: bigserial("id", { mode: "number" }).primaryKey(),
  ts: ts("ts").notNull().defaultNow(),
  tipo: text("tipo").notNull(),
  datos: jsonb("datos").$type<Record<string, unknown>>().notNull().default({}),
  procesado: ts("procesado"),
  resultado: jsonb("resultado").$type<unknown>(),
});

export const tablas = { usuarios, secretos, preferencias, estado, eventos, paper, corridas, reportes, comandos };
