/** Corrida del motor ya validada y con índices por ticker, lista para las pantallas. */
import {
  filaObjetivoSchema,
  filaOrdenSchema,
  filaRankingSchema,
  filaRentaFijaSchema,
  filas,
  metaSchema,
  type FilaObjetivo,
  type FilaOrden,
  type FilaRanking,
  type FilaRentaFija,
  type Meta,
} from "./schemas";

export interface CorridaCruda {
  stamp: string;
  creada: string;
  modo: string;
  meta: unknown;
  ranking: unknown;
  rentaFija: unknown;
  objetivos: unknown;
  ordenes: unknown;
  guia: string;
}

export interface Corrida {
  stamp: string;
  creada: string;
  modo: string;
  meta: Meta;
  ranking: FilaRanking[];
  rentaFija: FilaRentaFija[];
  objetivos: FilaObjetivo[];
  ordenes: FilaOrden[];
  guia: string;
  porTicker: Map<string, FilaRanking>;
  rfPorTicker: Map<string, FilaRentaFija>;
  objetivoPorTicker: Map<string, FilaObjetivo>;
  /** Nombre legible de bonos/letras (de la tabla de renta fija). */
  nombresRf: Record<string, string>;
}

export function prepararCorrida(c: CorridaCruda): Corrida {
  const meta = metaSchema.parse(c.meta ?? {});
  const ranking = filas(filaRankingSchema, c.ranking);
  const rentaFija = filas(filaRentaFijaSchema, c.rentaFija)
    .map((f) => ({ ...f, clave: f.ticker_iol ?? f.ticker ?? "" }))
    .filter((f) => f.clave);
  const objetivos = filas(filaObjetivoSchema, c.objetivos);
  const ordenes = filas(filaOrdenSchema, c.ordenes);
  const nombresRf: Record<string, string> = {};
  for (const f of rentaFija) if (f.nombre) nombresRf[f.clave] = f.nombre;
  return {
    stamp: c.stamp,
    creada: c.creada,
    modo: c.modo,
    meta,
    ranking,
    rentaFija,
    objetivos,
    ordenes,
    guia: c.guia,
    porTicker: new Map(ranking.map((f) => [f.ticker, f])),
    rfPorTicker: new Map(rentaFija.map((f) => [f.clave, f])),
    objetivoPorTicker: new Map(objetivos.filter((o) => o.ticker).map((o) => [o.ticker as string, o])),
    nombresRf,
  };
}
