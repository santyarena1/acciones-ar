/**
 * ¿Está frenado el operador? Detecta los problemas que le impiden operar y los explica en castellano llano,
 * con qué hacer. Puro: recibe los datos ya leídos.
 */
export interface ProblemaOperador {
  titulo: string;
  texto: string;
  enlace: { href: string; texto: string } | null;
}

export interface DatosProblema {
  modo: "paper" | "live";
  iolConectado: boolean;
  /** Último evento entre 'error' y 'corrida' (el más reciente), o null. */
  ultimo: { tipo: string; ts: string; error?: string | null } | null;
}

const CONECTAR = { href: "/configuracion#iol", texto: "Conectar IOL" };

export function problemaOperador(d: DatosProblema): ProblemaOperador | null {
  if (d.modo === "live" && !d.iolConectado) {
    return {
      titulo: "El operador está frenado: falta conectar tu cuenta de IOL",
      texto: "Está en modo real pero no tiene tu usuario y contraseña de IOL, así que no puede comprar ni vender. "
        + "Cargalos en Configuración y en la próxima revisión empieza a operar.",
      enlace: CONECTAR,
    };
  }
  if (!d.ultimo || d.ultimo.tipo !== "error") return null;
  return { titulo: "La última revisión del operador falló", ...explicarError(d.ultimo.error ?? "") };
}

function explicarError(error: string): Omit<ProblemaOperador, "titulo"> {
  if (/Faltan IOL_USERNAME|IOL_PASSWORD/.test(error)) {
    return { texto: "No encontró tus credenciales de IOL. Volvé a cargarlas en Configuración.", enlace: CONECTAR };
  }
  if (/SecretoIlegible|descifr/i.test(error)) {
    return { texto: "No pudo leer tus credenciales guardadas. Volvé a cargarlas en Configuración.", enlace: CONECTAR };
  }
  if (/Login IOL|HTTP 401|no autorizado/i.test(error)) {
    return {
      texto: "IOL rechazó el ingreso. Revisá que tu usuario y contraseña sigan siendo los mismos y que la API esté habilitada.",
      enlace: CONECTAR,
    };
  }
  if (/ModoRealNoHabilitado/.test(error)) {
    return { texto: "El modo real no está habilitado del todo. Revisalo en Configuración.", enlace: { href: "/configuracion#modo", texto: "Ver modo" } };
  }
  return {
    texto: "Hubo un problema técnico en la última revisión. El operador lo vuelve a intentar en la próxima; si se repite, avisá.",
    enlace: { href: "/historial", texto: "Ver historial" },
  };
}
