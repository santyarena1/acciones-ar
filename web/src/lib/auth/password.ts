import bcrypt from "bcryptjs";
import { z } from "zod";

const COSTO = 12;

export const emailSchema = z.string().trim().toLowerCase().pipe(z.email({ message: "Ese email no parece válido." }));
export const claveNuevaSchema = z
  .string()
  .min(10, "La contraseña tiene que tener al menos 10 caracteres.")
  .max(200, "La contraseña es demasiado larga.");

export function hashear(clave: string): Promise<string> {
  return bcrypt.hash(clave, COSTO);
}

export function coincide(clave: string, hash: string): Promise<boolean> {
  return bcrypt.compare(clave, hash);
}
