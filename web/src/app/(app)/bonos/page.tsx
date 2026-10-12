import Link from "next/link";
import { CurvaBonos, type PanelBonos, type PuntoBono } from "@/components/graficos/curva-bonos";
import { IconoAtras } from "@/components/iconos";
import { Descargo, Encabezado, Seccion, SinCorrida, Vacio } from "@/components/ui/piezas";
import type { FilaRentaFija } from "@/lib/domain/schemas";
import { contextoApp } from "@/lib/data/contexto";
import { anios, esNumero, mesAnio, pct, plata } from "@/lib/format";
import { CLASE_RF, CLASE_RF_CORTA, VALOR_RELATIVO } from "@/lib/labels";

export const metadata = { title: "Bonos y letras" };

const ORDEN = ["soberano_usd", "on_usd", "lecap", "boncap", "cer", "dual"] as const;
const DESCRIPCION: Record<string, string> = {
  soberano_usd: "Deuda del Estado nacional que paga en dólares. Rinde más cuanto más riesgo percibe el mercado.",
  on_usd: "Deuda de empresas (YPF, Pampa, etc.) en dólares. Suele ser más estable que la del Estado.",
  lecap: "Letras cortas del Tesoro en pesos a tasa fija: sabés hoy cuánto vas a cobrar.",
  boncap: "Como las Lecaps pero a más plazo.",
  cer: "Bonos en pesos que se ajustan por inflación: el rendimiento es lo que ganás por encima de ella.",
  dual: "Pagan lo mejor entre tasa fija y otra referencia.",
};

const COLOR: Record<string, string> = {
  soberano_usd: "var(--c-acciones_ar)",
  on_usd: "var(--c-cedears)",
  lecap: "var(--c-bonos_usd)",
  boncap: "var(--c-pesos)",
  cer: "var(--c-oro)",
  dual: "var(--c-caja)",
};

function puntos(filas: FilaRentaFija[], clases: string[]): PuntoBono[] {
  return filas
    .filter((f) => f.clase && clases.includes(f.clase) && esNumero(f.tir) && esNumero(f.duration) && f.duration > 0 && f.tir > -0.5 && f.tir < 2)
    .map((f) => ({
      ticker: f.clave,
      nombre: f.nombre ?? f.clave,
      clase: f.clase as string,
      tir: f.tir as number,
      duracion: f.duration as number,
      valor: f.senal_rv === "barato" || f.senal_rv === "caro" || f.senal_rv === "en_curva" ? f.senal_rv : null,
    }));
}

export default async function Bonos() {
  const { corrida: c } = await contextoApp();
  if (!c) {
    return (
      <>
        <Encabezado kicker="Bonos y letras" titulo="Renta fija" />
        <SinCorrida />
      </>
    );
  }
  const rf = c.rentaFija;
  const enCartera = new Set(Object.keys(c.meta.cartera.posiciones ?? {}));
  const paneles: PanelBonos[] = [
    { id: "usd", titulo: "En dólares", nota: "Rendimiento anual en dólares si lo mantenés hasta que vence.", clases: ["soberano_usd", "on_usd"] },
    { id: "fija", titulo: "Pesos a tasa fija", nota: "Rendimiento anual en pesos (sin descontar la inflación).", clases: ["lecap", "boncap", "dual"] },
    { id: "cer", titulo: "Pesos + inflación", nota: "Rendimiento anual por encima de la inflación.", clases: ["cer"] },
  ]
    .map((p) => ({
      id: p.id,
      titulo: p.titulo,
      nota: p.nota,
      clases: p.clases.filter((k) => rf.some((f) => f.clase === k)).map((k) => ({ id: k, nombre: CLASE_RF_CORTA[k] ?? k, color: COLOR[k] ?? "var(--ink-3)" })),
      puntos: puntos(rf, p.clases),
    }))
    .filter((p) => p.puntos.length > 0);

  return (
    <>
      <Encabezado kicker="Bonos y letras" titulo="Renta fija">
        Los bonos y letras que analiza el operador: cuánto rinden por año, a qué plazo y si están baratos frente a otros
        parecidos.
      </Encabezado>
      <nav className="entra -mt-2 mb-2 flex gap-2" aria-label="Secciones de mercado">
        <Link className="pastilla hover:!text-[var(--ink)]" href="/oportunidades">
          <IconoAtras width={13} height={13} /> Acciones y CEDEARs
        </Link>
        <span className="pastilla" aria-current="page">Bonos y letras</span>
      </nav>

      {paneles.length ? (
        <Seccion titulo="Rendimiento según plazo" bajada="Cada punto es un bono. Más arriba = rinde más; más a la derecha = tarda más en devolverte la plata.">
          <div className="hoja p-4 sm:p-6">
            <CurvaBonos paneles={paneles} />
          </div>
        </Seccion>
      ) : null}

      {rf.length === 0 ? (
        <div className="mt-8">
          <Vacio titulo="Sin datos de bonos en esta revisión">Se actualizan en la próxima.</Vacio>
        </div>
      ) : (
        ORDEN.filter((k) => rf.some((f) => f.clase === k)).map((k) => {
          const filas = rf
            .filter((f) => f.clase === k)
            .sort((a, b) => (b.score_rf ?? -1) - (a.score_rf ?? -1));
          return (
            <Seccion key={k} id={`rf-${k}`} titulo={CLASE_RF[k] ?? k} bajada={DESCRIPCION[k]}>
              <div className="hoja-plana desliza">
                <table className="tabla min-w-[680px]">
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th className="der">Rinde por año</th>
                      <th className="der">Plazo promedio</th>
                      <th>Vence</th>
                      <th className="der">Precio</th>
                      <th>Frente a parecidos</th>
                      <th className="der">Nota</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filas.map((f) => (
                      <tr key={f.clave}>
                        <td>
                          <Link href={`/activo/${encodeURIComponent(f.clave)}`} className="font-medium underline-offset-4 hover:underline">
                            {f.nombre ?? f.clave}
                          </Link>
                          <span className="mono ml-2 muted">{f.clave}</span>
                          {enCartera.has(f.clave) ? <span className="ml-2 text-[0.65rem] font-semibold uppercase tracking-wider" style={{ color: "var(--accent)" }}>tenés</span> : null}
                        </td>
                        <td className="der num font-semibold">{pct(f.tir)}</td>
                        <td className="der num soft">{anios(f.duration)}</td>
                        <td className="soft">{mesAnio(f.vencimiento)}</td>
                        <td className="der num soft">{plata(f.precio_ars, { decimales: f.precio_ars && f.precio_ars < 1000 ? 2 : 0 })}</td>
                        <td>
                          <ValorRelativo v={f.senal_rv} />
                        </td>
                        <td className="der num">
                          {f.apto_compra === false ? (
                            <span className="text-xs muted" title={f.motivo_no_apto ?? undefined}>
                              no apto
                            </span>
                          ) : esNumero(f.score_rf) ? (
                            <b>{Math.round(f.score_rf)}</b>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Seccion>
          );
        })
      )}
      <p className="mt-6 text-xs muted">
        “Nota” es el puntaje del operador (0 a 100) que combina rendimiento, precio frente a la curva y cuánto se opera. “No
        apto”: datos dudosos o muy poco volumen, no compra.
      </p>
      <Descargo />
    </>
  );
}

function ValorRelativo({ v }: { v: string | null }) {
  if (!v || !VALOR_RELATIVO[v]) return <span className="muted">—</span>;
  const tono = v === "barato" ? "sube" : v === "caro" ? "baja" : "neutro";
  return <span className="pastilla !h-6" data-tono={tono === "neutro" ? undefined : tono}>{VALOR_RELATIVO[v]}</span>;
}
