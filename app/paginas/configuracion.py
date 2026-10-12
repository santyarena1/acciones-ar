"""Configuración: conexión con IOL, modo práctica/real, perfil, pausa y Telegram."""
import streamlit as st

from app import credenciales as cred
from app.comun import banda, bitacora, descargo, estado_operador
from app.etiquetas import PERFIL
from src.config import guardar_preferencias, load_settings

st.markdown('<div class="kicker">Configuración</div>', unsafe_allow_html=True)
st.title("Configuración")
s, e = load_settings(), estado_operador()

# --- 1. IOL ---------------------------------------------------------------------------------------------
st.subheader("1. Tu cuenta de IOL")
if cred.configurado(*cred.CLAVES_IOL):
    banda(f"Conectado con el usuario <b>{cred.usuario_iol()}</b>. La clave está guardada solo en esta PC.", "ok")
    c1, c2 = st.columns(2)
    if c1.button("Probar conexión"):
        from dotenv import dotenv_values
        v = dotenv_values(cred.ENV)
        ok, msg = cred.probar_iol(v.get("IOL_USERNAME", ""), v.get("IOL_PASSWORD", ""))
        (st.success if ok else st.error)(msg)
    if c2.button("Desconectar IOL"):
        cred.borrar(*cred.CLAVES_IOL)
        cred.habilitar_modo_real(False)
        st.rerun()
else:
    st.caption("Son los mismos datos con los que entrás a invertironline.com. Antes tenés que tener habilitada la "
               "API: en IOL andá a **Mi cuenta → Consultas**, elegí tipo *Mi cuenta* y motivo *API*, y pedí el alta.")
    with st.form("iol"):
        usuario = st.text_input("Usuario de IOL")
        clave = st.text_input("Contraseña de IOL", type="password")
        if st.form_submit_button("Guardar y probar", type="primary"):
            ok, msg = cred.probar_iol(usuario.strip(), clave)
            if ok:
                cred.guardar(IOL_USERNAME=usuario.strip(), IOL_PASSWORD=clave)
                st.success(msg)
                st.rerun()
            else:
                st.error(msg + " No se guardó nada.")

# --- 2. modo --------------------------------------------------------------------------------------------
st.subheader("2. Práctica o plata real")
if e["real"]:
    banda("El operador está usando <b>tu cuenta real de IOL</b>: compra y vende solo.", "mal")
    if st.button("Volver a modo práctica"):
        guardar_preferencias({"operador": {"modo": "paper"}})
        cred.habilitar_modo_real(False)
        st.rerun()
else:
    st.caption("En práctica opera con $10 millones simulados, con las mismas reglas que en real.")
    if not cred.configurado(*cred.CLAVES_IOL):
        st.info("Para operar con plata real primero conectá tu cuenta de IOL (punto 1).")
    else:
        with st.form("real"):
            st.markdown("Al activar el modo real, el operador **va a comprar y vender solo en tu cuenta de IOL**, "
                        "con todo el dinero disponible, cada vez que su análisis lo indique. Puede ganar y puede perder.")
            entiendo = st.checkbox("Entiendo que el operador maneja mi cuenta de IOL de forma automática")
            palabra = st.text_input("Para confirmar escribí ACTIVAR")
            if st.form_submit_button("Activar modo real"):
                if entiendo and palabra.strip().upper() == "ACTIVAR":
                    guardar_preferencias({"operador": {"modo": "live"}})
                    cred.habilitar_modo_real(True)
                    bitacora().registrar("modo_real", activado=True)
                    st.rerun()
                else:
                    st.error("Tenés que tildar la casilla y escribir ACTIVAR.")

# --- ingresar plata --------------------------------------------------------------------------------------
st.subheader("Ingresar plata")
if e["real"]:
    st.markdown("Transferí a tu cuenta de IOL como siempre. **El operador detecta el depósito solo** en la próxima "
                "revisión (cada 15 minutos con el mercado abierto), te avisa y lo invierte según el plan.")
else:
    st.caption("En práctica podés simular un depósito para ver cómo lo detecta y lo invierte.")
    with st.form("deposito"):
        monto = st.number_input("Monto a depositar (práctica)", min_value=0, step=50_000, value=100_000)
        if st.form_submit_button("Simular depósito") and monto > 0:
            from src.servicio import crear_broker
            crear_broker("paper", s).depositar(float(monto))
            st.success(f"Listo: ingresaron ${monto:,.0f} a la cuenta de práctica. El operador los va a detectar e "
                       "invertir en la próxima revisión.".replace(",", "."))
with st.expander("Corregir el total que pusiste"):
    st.caption("Si el operador no detectó bien algún depósito o retiro, poné acá cuánto pusiste en total. "
               "Se usa solo para calcular tu ganancia real.")
    total_nuevo = st.number_input("Total aportado", min_value=0, step=10_000, value=int(e.get("aportes") or 0))
    if st.button("Guardar total"):
        b = bitacora()
        aportes = b.estado().get("aportes") or {}
        modo_k = "live" if e["real"] else "paper"
        aportes[modo_k] = {**aportes.get(modo_k, {}), "total": float(total_nuevo)}
        b.guardar_estado(aportes=aportes)
        b.registrar("aporte_corregido", modo=modo_k, total=float(total_nuevo))
        st.success("Guardado.")

# --- 3. perfil ------------------------------------------------------------------------------------------
st.subheader("3. Perfil de riesgo")
perfiles = list(s["perfiles"])
actual = s.get("operador", {}).get("perfil", "moderado")
elegido = st.radio("¿Cuánto riesgo querés tomar?", perfiles, index=perfiles.index(actual),
                   format_func=lambda p: PERFIL.get(p, p))
if elegido != actual:
    guardar_preferencias({"operador": {"perfil": elegido}})
    st.success("Guardado. Se aplica en la próxima revisión.")

# --- 4. pausa -------------------------------------------------------------------------------------------
st.subheader("4. Pausar el operador")
pausado = st.toggle("Operador en pausa (no compra ni vende)", value=e["pausado"])
if pausado != e["pausado"]:
    (bitacora().pausar("desde la app") if pausado else bitacora().reanudar())
    st.rerun()

# --- 5. Telegram ----------------------------------------------------------------------------------------
st.subheader("5. Avisos por Telegram")
st.caption("Se activa cuando la plataforma esté online (Vercel). Podés dejarlo configurado desde ahora.")
with st.expander("Cómo crear tu bot (2 minutos)"):
    st.markdown("1. En Telegram buscá **@BotFather** y mandale `/newbot`.\n"
                "2. Elegí un nombre y un usuario que termine en `bot`.\n"
                "3. Copiá el **token** que te da y pegalo abajo.\n"
                "4. Mandale cualquier mensaje a tu bot nuevo y tocá **Buscar mi chat**.")
tg_ok = cred.configurado(*cred.CLAVES_TELEGRAM)
if tg_ok:
    banda("Telegram configurado.", "ok")
with st.form("tg"):
    token = st.text_input("Token del bot", type="password", placeholder="guardado" if tg_ok else "")
    c1, c2 = st.columns(2)
    buscar = c1.form_submit_button("Buscar mi chat y guardar")
    probar = c2.form_submit_button("Mandar mensaje de prueba")
    if buscar and token:
        chat = cred.buscar_chat_id(token.strip())
        if chat:
            cred.guardar(TELEGRAM_TOKEN=token.strip(), TELEGRAM_CHAT_ID=chat)
            st.success("Listo, encontré tu chat y quedó guardado.")
        else:
            st.error("No encontré mensajes: escribile algo a tu bot y volvé a intentar.")
    if probar:
        from dotenv import dotenv_values
        v = dotenv_values(cred.ENV)
        ok, msg = cred.probar_telegram(token.strip() or v.get("TELEGRAM_TOKEN", ""), v.get("TELEGRAM_CHAT_ID", ""))
        (st.success if ok else st.error)(msg)
descargo()
