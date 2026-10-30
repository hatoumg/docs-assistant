import { HttpError, badRequest, notFound } from "./errors.js";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/;
export const ALLOWED_EXTENSIONS = [".md", ".txt", ".pdf"];

/** An id in a web address. A malformed one is "not found", the same as an id that does not exist. */
export function parseUuid(value: unknown, what = "Item"): string {
  if (typeof value !== "string" || !UUID.test(value)) throw notFound(what);
  return value.toLowerCase();
}

export function parseId(value: unknown, what = "Item"): number {
  if (typeof value !== "string" || !/^[1-9]\d{0,8}$/.test(value)) throw notFound(what);
  return Number(value);
}

/** A folder or file name: trimmed, 1 to `max` characters, no slashes or control characters. */
export function cleanName(value: unknown, what: string, max = 120): string {
  if (typeof value !== "string") throw badRequest(`${what} must be text.`);
  const name = value.normalize("NFC").trim();
  if (name.length < 1 || name.length > max) throw badRequest(`${what} must be 1 to ${max} characters.`);
  if (CONTROL_CHARACTERS.test(name) || /[\\/]/.test(name)) throw badRequest(`${what} cannot contain slashes or control characters.`);
  return name;
}

export function cleanFileName(value: unknown): { name: string; extension: string } {
  const name = cleanName(value, "File name", 180);
  const dot = name.lastIndexOf(".");
  const extension = dot > 0 ? name.slice(dot).toLowerCase() : "";
  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    throw new HttpError(415, "unsupported_type", `Only ${ALLOWED_EXTENSIONS.slice(0, -1).join(", ")} and ${ALLOWED_EXTENSIONS[ALLOWED_EXTENSIONS.length - 1]} files can be uploaded.`);
  }
  return { name, extension };
}

export function cleanEmail(value: unknown): string {
  if (typeof value !== "string") throw badRequest("Enter your email address.");
  const email = value.trim().toLowerCase();
  if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw badRequest("Enter a valid email address.");
  return email;
}

export function cleanPassword(value: unknown): string {
  if (typeof value !== "string" || value.length < 8 || value.length > 128) {
    throw badRequest("The password must be 8 to 128 characters.");
  }
  return value;
}

export function cleanQuestion(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) throw badRequest("Type a question first.");
  if (value.length > 2000) throw badRequest("The question is too long (2000 characters at most).");
  return value.trim();
}
