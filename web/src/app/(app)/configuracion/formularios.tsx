"use client";

import { useActionState, useState } from "react";
import {
  buscarChatTelegram,
  prepararTelegram,
  conectarIol,
  conectarWebhook,
  desconectarIol,
  desconectarTelegram,
  probarIolGuardado,
  probarTelegram,
} from "@/app/acciones/cuentas";
import {
  activarReal,
  cambiarPerfil,
  corregirAportado,
  depositarPractica,
  pausar,
  reanudar,
  reiniciarPractica,
  revisarAhora,
  volverPractica,
} from "@/app/acciones/operador";
import { IconoPausa, IconoPlay, IconoRefrescar } from "@/components/iconos";
import { BotonEnviar, Campo, FormAccion, Mensaje } from "@/components/ui/formulario";
import type { Respuesta } from "@/lib/acciones";
import { pct } from "@/lib/format";
import { CLASE_CORTA } from "@/lib/labels";
import type { Perfil, PerfilId } from "@/lib/perfiles";

export function Controles({ pausado }: { pausado: boolean }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <FormAccion accion={revisarAhora} className="hoja-plana grid content-between gap-3 p-4">
        <div>
          <p className="font-semibold">Revisar ahora</p>
          <p className="mt-0.5 text-sm muted">Que analice el mercado y opere si hace falta, sin esperar a la próxima hora.</p>
        </div>
        <BotonEnviar className="btn btn-primario" pendiente="Pidiendo…">
          <IconoRefrescar width={17} height={17} /> Revisar ahora
        </BotonEnviar>
      </FormAccion>
      <FormAccion accion={pausado ? reanudar : pausar} className="hoja-plana grid content-between gap-3 p-4">
        <div>
          <p className="font-semibold">{pausado ? "El operador está en pausa" : "Pausar el operador"}</p>
          <p className="mt-0.5 text-sm muted">
            {pausado ? "No compra ni vende. Tus inversiones quedan como están." : "Deja de comprar y vender. No vende nada por pausar."}
          </p>
        </div>
        <BotonEnviar className={pausado ? "btn btn-acento" : "btn"} pendiente="Guardando…">
          {pausado ? (
            <>
              <IconoPlay width={17} height={17} /> Reanudar
            </>
          ) : (
            <>
              <IconoPausa width={17} height={17} /> Pausar
            </>
          )}
        </BotonEnviar>
      </FormAccion>
    </div>
  );
}

export function ElegirPerfil({ perfiles, actual }: { perfiles: readonly Perfil[]; actual: PerfilId }) {
  const [elegido, setElegido] = useState<PerfilId>(actual);
  return (
    <FormAccion accion={cambiarPerfil} className="grid gap-4">
      <fieldset className="grid gap-2.5 md:grid-cols-2">
        <legend className="sr-only">Perfil de riesgo</legend>
        {perfiles.map((p) => {
          const on = elegido === p.id;
          return (
            <label
              key={p.id}
              className="relative grid cursor-pointer gap-3 rounded-[var(--radius)] border p-4 transition-[box-shadow,border-color,background]"
              style={{
                borderColor: on ? "var(--accent)" : "var(--line)",
                background: on ? "var(--bg-sheet)" : "transparent",
                boxShadow: on ? "0 0 0 1px var(--accent), var(--shadow)" : undefined,
              }}
            >
              <input type="radio" name="perfil" value={p.id} checked={on} onChange={() => setElegido(p.id)} className="sr-only" />
              <span className="flex items-baseline justify-between gap-2">
                <span className="text-[1.05rem] font-semibold">{p.nombre}</span>
                {p.id === actual ? <span className="text-[0.65rem] font-semibold uppercase tracking-wider" style={{ color: "var(--accent)" }}>actual</span> : null}
              </span>
              <span className="text-sm soft">{p.descripcion}</span>
              <span className="flex h-2 gap-[2px] overflow-hidden rounded-full" aria-hidden="true">
                {Object.entries(p.reparto).map(([k, v]) => (
                  <span key={k} className="h-full first:rounded-l-full last:rounded-r-full" style={{ flex: `${v} 1 0`, background: k === "caja" ? "var(--c-caja)" : `var(--c-${k})` }} />
                ))}
              </span>
              <span className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs muted">
                {Object.entries(p.reparto).map(([k, v]) => (
                  <span key={k} className="num">
                    {CLASE_CORTA[k]} {pct(v, { decimales: 0 })}
                  </span>
                ))}
              </span>
            </label>
          );
        })}
      </fieldset>
      <div>
        <BotonEnviar className="btn btn-primario" disabled={elegido === actual} pendiente="Guardando…">
          Usar este perfil
        </BotonEnviar>
      </div>
    </FormAccion>
  );
}

export function Plata({ modo }: { modo: "paper" | "live" }) {
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      {modo === "paper" ? (
        <FormAccion accion={depositarPractica} className="hoja-plana grid gap-3 p-4" limpiarAlOk>
          {(e) => (
            <>
              <p className="font-semibold">Sumar plata a la práctica</p>
              <Campo nombre="monto" etiqueta="Monto en pesos" inputMode="numeric" placeholder="Ej: 100.000" required error={e.errores?.monto} autoComplete="off" />
              <BotonEnviar className="btn btn-primario">Sumar</BotonEnviar>
            </>
          )}
        </FormAccion>
      ) : (
        <div className="hoja-plana grid gap-2 p-4">
          <p className="font-semibold">¿Querés invertir más?</p>
          <p className="text-sm soft">
            Transferí la plata a tu cuenta de IOL como siempre (desde tu banco, a tu CVU/CBU de IOL). El operador detecta el
            depósito en su próxima revisión y lo invierte según tu perfil. No hace falta hacer nada más acá.
          </p>
        </div>
      )}
      <FormAccion accion={corregirAportado} className="hoja-plana grid gap-3 p-4" limpiarAlOk>
        {(e) => (
          <>
            <div>
              <p className="font-semibold">Corregir el total que pusiste</p>
              <p className="mt-0.5 text-sm muted">Si el operador contó mal tus depósitos, poné acá el total real que pusiste. Con esto calcula tu ganancia.</p>
            </div>
            <Campo nombre="total" etiqueta="Total aportado en pesos" inputMode="numeric" placeholder="Ej: 500.000" required error={e.errores?.total} autoComplete="off" />
            <BotonEnviar className="btn">Corregir</BotonEnviar>
          </>
        )}
      </FormAccion>
      {modo === "paper" ? (
        <FormAccion accion={reiniciarPractica} className="hoja-plana grid gap-3 p-4 lg:col-span-2" limpiarAlOk>
          {(e) => (
            <>
              <div>
                <p className="font-semibold">Reiniciar la práctica</p>
                <p className="mt-0.5 text-sm muted">Borra la cartera de práctica y arranca de cero con el monto que elijas. No toca tu cuenta real.</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
                <Campo nombre="capital" etiqueta="Capital inicial en pesos" inputMode="numeric" defaultValue="500.000" required error={e.errores?.capital} autoComplete="off" />
                <label className="flex min-h-[46px] items-center gap-2 text-sm">
                  <input type="checkbox" name="confirmo" value="si" className="h-4 w-4 accent-[var(--loss)]" /> Sí, quiero empezar de cero
                </label>
              </div>
              {e.errores?.confirmo ? <p className="error-campo">{e.errores.confirmo}</p> : null}
              <div>
                <BotonEnviar className="btn">Reiniciar práctica</BotonEnviar>
              </div>
            </>
          )}
        </FormAccion>
      ) : null}
    </div>
  );
}

export function CuentaIol({ conectada }: { conectada: boolean }) {
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
      <div className="grid gap-3">
        {conectada ? (
          <div className="hoja-plana grid gap-3 p-4">
            <p className="flex items-center gap-2 font-semibold">
              <span className="h-2 w-2 rounded-full" style={{ background: "var(--gain)" }} aria-hidden="true" /> Cuenta conectada
            </p>
            <p className="text-sm muted">Tu usuario y contraseña están guardados cifrados. Nadie los puede ver, ni siquiera desde esta pantalla.</p>
            <div className="flex flex-wrap gap-2">
              <FormAccion accion={probarIolGuardado}>
                <BotonEnviar className="btn btn-chico" pendiente="Probando…">
                  Probar conexión
                </BotonEnviar>
              </FormAccion>
              <FormAccion accion={desconectarIol}>
                <BotonEnviar className="btn btn-chico btn-texto" pendiente="Borrando…">
                  Desconectar
                </BotonEnviar>
              </FormAccion>
            </div>
          </div>
        ) : null}
        <FormAccion accion={conectarIol} className="hoja-plana grid gap-3 p-4" limpiarAlOk>
          {(e) => (
            <>
              <p className="font-semibold">{conectada ? "Cambiar usuario o contraseña" : "Conectar tu cuenta"}</p>
              <Campo nombre="usuario" etiqueta="Usuario de IOL" autoComplete="off" autoCapitalize="none" spellCheck={false} required error={e.errores?.usuario} />
              <Campo nombre="clave" etiqueta="Contraseña de IOL" type="password" autoComplete="off" required error={e.errores?.clave} />
              <p className="ayuda">Primero probamos que funcione; solo si IOL responde bien, lo guardamos (cifrado).</p>
              <BotonEnviar className="btn btn-primario" pendiente="Probando con IOL…">
                Probar y guardar
              </BotonEnviar>
            </>
          )}
        </FormAccion>
      </div>
      <aside className="rounded-[var(--radius)] border border-dashed p-5 text-sm leading-relaxed" style={{ borderColor: "var(--line-strong)" }}>
        <p className="kicker mb-2">Antes: habilitá la API en IOL</p>
        <ol className="grid list-decimal gap-1.5 pl-5 soft">
          <li>Entrá a invertironline.com con tu usuario.</li>
          <li>
            Andá a <b>Mi cuenta → Consultas</b>.
          </li>
          <li>
            Creá una consulta nueva: tipo <b>“Mi cuenta”</b>, motivo <b>“API”</b>, y pedí que te habiliten el acceso por API.
          </li>
          <li>Cuando te confirmen (suele tardar uno o dos días hábiles), volvé acá y conectá la cuenta.</li>
        </ol>
      </aside>
    </div>
  );
}

export function ModoReal({ modo, iolConectada, desde }: { modo: "paper" | "live"; iolConectada: boolean; desde: string | null }) {
  if (modo === "live") {
    return (
      <div className="aviso" data-tono="peligro">
        <span />
        <div className="grid gap-3">
          <div>
            <p className="font-semibold">Modo real activo</p>
            <p className="text-sm soft">
              El operador compra y vende en tu cuenta de IOL{desde ? ` desde el ${new Date(desde).toLocaleDateString("es-AR")}` : ""}. Podés volver a la práctica cuando quieras: no vende nada por eso.
            </p>
          </div>
          <FormAccion accion={volverPractica}>
            <BotonEnviar className="btn" pendiente="Cambiando…">
              Volver a modo práctica
            </BotonEnviar>
          </FormAccion>
        </div>
      </div>
    );
  }
  return (
    <FormAccion accion={activarReal} className="hoja-plana grid gap-4 p-5" limpiarAlOk>
      {(e) => (
        <>
          <div>
            <p className="font-semibold">Ahora estás en práctica</p>
            <p className="mt-0.5 text-sm soft">
              Con el modo real, el operador compra y vende <b>solo</b>, con tu plata, en tu cuenta de IOL. Lo hace con
              protecciones (nunca gasta más de lo que hay, no repite órdenes, controla precios), pero invertir siempre tiene riesgo.
            </p>
          </div>
          {!iolConectada ? (
            <p className="text-sm" style={{ color: "var(--warn)" }}>
              Para activarlo primero tenés que conectar tu cuenta de IOL (arriba).
            </p>
          ) : null}
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" name="entiendo" value="si" className="mt-0.5 h-4 w-4 flex-none accent-[var(--loss)]" disabled={!iolConectada} />
            <span>Entiendo que el operador maneja mi cuenta de IOL de forma automática.</span>
          </label>
          {e.errores?.entiendo ? <p className="error-campo -mt-2">{e.errores.entiendo}</p> : null}
          <Campo
            nombre="palabra"
            etiqueta="Para confirmar, escribí ACTIVAR"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            disabled={!iolConectada}
            error={e.errores?.palabra}
          />
          <div>
            <BotonEnviar className="btn btn-peligro" disabled={!iolConectada} pendiente="Activando…">
              Activar modo real
            </BotonEnviar>
          </div>
        </>
      )}
    </FormAccion>
  );
}

export function Telegram({ conectado }: { conectado: boolean }) {
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1fr)]">
      <ol className="grid gap-4 text-sm leading-relaxed">
        {[
          <>
            En Telegram, buscá <b>@BotFather</b> y abrí el chat.
          </>,
          <>
            Mandale <b className="mono">/newbot</b>, elegí un nombre (ej. “Mi operador”) y un usuario que termine en “bot”.
          </>,
          <>BotFather te da un token (números, dos puntos y letras). Copialo y pegalo acá y tocá “Seguir”.</>,
          <>
            Te vamos a dar un código: mandáselo a tu bot (así nadie más se puede hacer pasar por vos) y tocá “Buscar mi chat”.
          </>,
        ].map((paso, i) => (
          <li key={i} className="grid grid-cols-[2rem_1fr] gap-2">
            <span className="display num text-2xl leading-none" style={{ color: "var(--accent)" }}>
              {i + 1}
            </span>
            <span className="soft">{paso}</span>
          </li>
        ))}
      </ol>
      <div className="grid content-start gap-3">
        <VincularBot conectado={conectado} />
        {conectado ? (
          <div className="hoja-plana grid gap-3 p-4">
            <p className="flex items-center gap-2 font-semibold">
              <span className="h-2 w-2 rounded-full" style={{ background: "var(--gain)" }} aria-hidden="true" /> Bot conectado
            </p>
            <div className="flex flex-wrap gap-2">
              <FormAccion accion={probarTelegram}>
                <BotonEnviar className="btn btn-chico" pendiente="Enviando…">
                  Mandar prueba
                </BotonEnviar>
              </FormAccion>
              <FormAccion accion={conectarWebhook}>
                <BotonEnviar className="btn btn-chico" pendiente="Conectando…">
                  Activar comandos
                </BotonEnviar>
              </FormAccion>
              <FormAccion accion={desconectarTelegram}>
                <BotonEnviar className="btn btn-chico btn-texto" pendiente="Borrando…">
                  Desconectar
                </BotonEnviar>
              </FormAccion>
            </div>
            <p className="ayuda">
              “Activar comandos” te deja escribirle al bot: /estado, /cartera, /hoy, /pausar, /reanudar, /revisar y /ayuda.
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

const VACIO: Respuesta = { ok: false, mensaje: "" };

/** Vinculación en dos pasos: token -> código de un solo bot -> buscar el chat que mandó ese código. */
function VincularBot({ conectado }: { conectado: boolean }) {
  const [token, setToken] = useState("");
  const [paso1, preparar] = useActionState(prepararTelegram, VACIO);
  const [paso2, buscar] = useActionState(buscarChatTelegram, VACIO);
  const codigo = paso1.ok ? paso1.datos?.codigo : undefined;
  return (
    <div className="hoja-plana grid gap-3 p-4">
      <p className="font-semibold">{conectado ? "Cambiar de bot" : "Conectar tu bot"}</p>
      <form action={preparar} className="grid gap-3" noValidate>
        <Campo
          nombre="token"
          etiqueta="Token del bot"
          autoComplete="off"
          spellCheck={false}
          placeholder="123456789:ABC..."
          required
          value={token}
          onChange={(e) => setToken(e.target.value)}
          error={paso1.errores?.token}
        />
        {!codigo ? (
          <BotonEnviar className="btn btn-primario" pendiente="Revisando…">
            Seguir
          </BotonEnviar>
        ) : null}
        {!paso1.ok ? <Mensaje estado={paso1} /> : null}
      </form>
      {codigo ? (
        <form action={buscar} className="grid gap-3">
          <input type="hidden" name="token" value={token} />
          <div className="rounded-[var(--radius-sm)] p-3 text-sm" style={{ background: "var(--accent-wash)" }}>
            Mandale a <b>@{paso1.datos?.bot}</b> este mensaje:
            <p className="mono mt-1 select-all text-lg font-semibold tracking-wider">/start {codigo}</p>
          </div>
          <BotonEnviar className="btn btn-primario" pendiente="Buscando…">
            Buscar mi chat
          </BotonEnviar>
          <Mensaje estado={paso2} />
        </form>
      ) : null}
    </div>
  );
}
