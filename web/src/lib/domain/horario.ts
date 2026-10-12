/**
 * Cuándo es la próxima revisión del operador (supuesto: cada hora a los :30, de 11:30 a 16:30, lunes a viernes,
 * hora Argentina, UTC−3 sin horario de verano). Los feriados no se conocen acá: es una estimación para mostrar.
 */
const PRIMERA = 11;
const ULTIMA = 16;
const MINUTO = 30;
const OFFSET_AR_MS = -3 * 60 * 60 * 1000;

export interface ProximaRevision {
  fecha: Date;
  /** "hoy a las 14:30", "mañana a las 11:30", "el lunes a las 11:30" */
  texto: string;
}

const DIAS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];

export function proximaRevision(ahora = new Date()): ProximaRevision {
  // trabajamos con un "reloj argentino" corriendo en UTC
  const ar = new Date(ahora.getTime() + OFFSET_AR_MS);
  const candidato = new Date(Date.UTC(ar.getUTCFullYear(), ar.getUTCMonth(), ar.getUTCDate(), ar.getUTCHours(), MINUTO));
  if (candidato.getTime() <= ar.getTime()) candidato.setUTCHours(candidato.getUTCHours() + 1);
  for (let i = 0; i < 24 * 8; i++) {
    const dia = candidato.getUTCDay();
    const h = candidato.getUTCHours();
    if (dia >= 1 && dia <= 5 && h >= PRIMERA && h <= ULTIMA) break;
    candidato.setUTCHours(candidato.getUTCHours() + 1);
    candidato.setUTCMinutes(MINUTO);
  }
  const fecha = new Date(candidato.getTime() - OFFSET_AR_MS);
  const hh = `${String(candidato.getUTCHours()).padStart(2, "0")}:${String(MINUTO).padStart(2, "0")}`;
  const diaAr = Date.UTC(ar.getUTCFullYear(), ar.getUTCMonth(), ar.getUTCDate());
  const diaCand = Date.UTC(candidato.getUTCFullYear(), candidato.getUTCMonth(), candidato.getUTCDate());
  const dif = Math.round((diaCand - diaAr) / 86_400_000);
  const cuando = dif === 0 ? "hoy" : dif === 1 ? "mañana" : `el ${DIAS[candidato.getUTCDay()]}`;
  return { fecha, texto: `${cuando} a las ${hh}` };
}
