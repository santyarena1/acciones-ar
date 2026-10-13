import { Descargo, Encabezado, Seccion } from "@/components/ui/piezas";
import { comandosPendientes } from "@/lib/data/comandos";
import { contextoApp } from "@/lib/data/contexto";
import { secretosCargados } from "@/lib/data/secretos";
import { haceCuanto, plata } from "@/lib/format";
import { PERFILES } from "@/lib/perfiles";
import { Controles, CuentaIol, ElegirPerfil, ModoReal, Plata, Telegram } from "./formularios";

export const metadata = { title: "Configuración" };

const INDICE = [
  ["revisar", "Controles"],
  ["perfil", "Perfil de riesgo"],
  ["plata", "Plata"],
  ["iol", "Cuenta de IOL"],
  ["modo", "Práctica o real"],
  ["telegram", "Avisos por Telegram"],
] as const;

const NOMBRE_COMANDO: Record<string, string> = {
  revisar: "Revisar ahora",
  depositar_practica: "Sumar plata a la práctica",
  reiniciar_practica: "Reiniciar la práctica",
};

export default async function Configuracion() {
  const ctx = await contextoApp(); // exige sesión antes de leer nada más
  const [secretos, pendientes] = await Promise.all([secretosCargados(), comandosPendientes()]);
  const iol = Boolean(secretos.IOL_USERNAME && secretos.IOL_PASSWORD);
  const telegram = Boolean(secretos.TELEGRAM_TOKEN && secretos.TELEGRAM_CHAT_ID);

  return (
    <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_13rem] lg:gap-12">
      <div className="min-w-0">
        <Encabezado kicker="Configuración" titulo="Cómo trabaja tu operador">
          Todo lo que podés decidir vos. Los cambios se aplican en la próxima revisión.
        </Encabezado>

        <Seccion id="revisar" titulo="Controles">
          <Controles pausado={ctx.estado.pausado} />
          {pendientes.length ? (
            <div className="mt-3 text-sm muted" aria-live="polite">
              <p className="font-medium soft">Pedidos en espera:</p>
              <ul className="mt-1 grid gap-0.5">
                {pendientes.map((p) => (
                  <li key={p.id}>
                    {NOMBRE_COMANDO[p.tipo] ?? p.tipo}
                    {typeof p.datos.monto === "number" ? ` (${plata(p.datos.monto)})` : ""}
                    {typeof p.datos.capital === "number" ? ` (${plata(p.datos.capital)})` : ""} — pedido {haceCuanto(p.ts)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </Seccion>

        <Seccion id="perfil" titulo="Perfil de riesgo" bajada="Define cómo se reparte la plata entre acciones, bonos y pesos.">
          <ElegirPerfil perfiles={PERFILES} actual={ctx.perfil} />
        </Seccion>

        <Seccion id="plata" titulo="Plata" bajada={ctx.modo === "paper" ? "En práctica podés simular depósitos." : "En modo real la plata entra por IOL."}>
          <Plata modo={ctx.modo} />
        </Seccion>

        <Seccion id="iol" titulo="Cuenta de IOL" bajada="Necesaria para el modo real. Se guarda cifrada.">
          <CuentaIol conectada={iol} />
        </Seccion>

        <Seccion id="modo" titulo="Práctica o real">
          <ModoReal modo={ctx.modo} iolConectada={iol} desde={ctx.estado.modoReal.desde} />
        </Seccion>

        <Seccion id="telegram" titulo="Avisos por Telegram" bajada="Te avisa cuando compra, vende, pide plata o hay una caída fuerte. Y le podés dar órdenes.">
          <Telegram conectado={telegram} />
        </Seccion>
        <Descargo />
      </div>

      <nav aria-label="En esta página" className="hidden lg:block">
        <div className="sticky top-10 mt-[8.5rem] grid gap-1 border-l pl-4 text-sm">
          <p className="kicker mb-2">En esta página</p>
          {INDICE.map(([id, label]) => (
            <a key={id} href={`#${id}`} className="py-1 soft hover:text-[var(--ink)]">
              {label}
            </a>
          ))}
        </div>
      </nav>
    </div>
  );
}

// "Revisar ahora" dispara el motor con after(): la función sigue viva hasta que termina (~1 min)
export const maxDuration = 300;
