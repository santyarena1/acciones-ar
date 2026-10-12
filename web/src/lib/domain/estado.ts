/** Estado del operador (tabla `estado`, clave/valor) interpretado. Puro: testeable sin base. */
import { esNumero } from "../format";
import {
  aportesSchema,
  modoRealSchema,
  pausadoSchema,
  pedidoFondosSchema,
  seguimientoSchema,
  type Modo,
} from "./schemas";

export interface EstadoOperador {
  pausado: boolean;
  motivoPausa: string | null;
  modoReal: { habilitado: boolean; desde: string | null };
  aportes: ReturnType<typeof aportesSchema.parse>;
  seguimiento: ReturnType<typeof seguimientoSchema.parse>;
  pedidoFondos: ReturnType<typeof pedidoFondosSchema.parse>;
  ultimoRebalanceo: string | null;
}

/** Igual que el motor: una pausa ilegible cuenta como pausado (falla cerrado). */
export function interpretarEstado(filas: Record<string, unknown>): EstadoOperador {
  let pausado = false;
  let motivoPausa: string | null = null;
  if ("pausado" in filas) {
    const p = pausadoSchema.safeParse(filas.pausado);
    if (p.success) {
      pausado = p.data.pausado;
      motivoPausa = p.data.motivo ?? null;
    } else {
      pausado = true;
      motivoPausa = "estado de pausa ilegible";
    }
  }
  const mr = modoRealSchema.safeParse(filas.modo_real);
  return {
    pausado,
    motivoPausa,
    modoReal: mr.success
      ? { habilitado: mr.data.habilitado, desde: mr.data.desde ?? null }
      : { habilitado: false, desde: null },
    aportes: aportesSchema.parse(filas.aportes ?? {}),
    seguimiento: seguimientoSchema.parse(filas.seguimiento ?? {}),
    pedidoFondos: pedidoFondosSchema.parse(filas.ultimo_pedido_fondos ?? null),
    ultimoRebalanceo: typeof filas.ultimo_rebalanceo === "string" ? filas.ultimo_rebalanceo : null,
  };
}

export interface Rendimiento {
  valor: number | null;
  aportado: number | null;
  ganancia: number | null;
  gananciaPct: number | null;
  /** Rendimiento del operador sin contar depósitos (índice − 1). */
  operador: number | null;
  /** "No hacer nada": mitad S&P 500, mitad Merval. */
  noHacerNada: number | null;
  diferencia: number | null;
  caidaDesdeMaximo: number | null;
}

/** Ganancia real (valor − aportes) y comparación contra no hacer nada. Port de aportes.rendimiento + seguimiento.resumen. */
export function rendimiento(e: EstadoOperador, modo: Modo, valorTotal: number | null | undefined): Rendimiento {
  const aportado = e.aportes[modo]?.total;
  const valor = esNumero(valorTotal) ? valorTotal : null;
  const tieneAporte = esNumero(aportado) && aportado > 0;
  const ganancia = tieneAporte && valor !== null ? valor - aportado : null;
  const s = e.seguimiento[modo];
  const operador = esNumero(s?.indice) ? s.indice - 1 : null;
  const noHacerNada = esNumero(s?.bm_indice) ? s.bm_indice - 1 : null;
  return {
    valor,
    aportado: esNumero(aportado) ? aportado : null,
    ganancia,
    gananciaPct: ganancia !== null && tieneAporte ? ganancia / aportado : null,
    operador,
    noHacerNada,
    diferencia: operador !== null && noHacerNada !== null ? operador - noHacerNada : null,
    caidaDesdeMaximo: esNumero(s?.indice) && esNumero(s?.pico) && s.pico > 0 ? s.indice / s.pico - 1 : null,
  };
}
