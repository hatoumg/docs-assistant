import type { IncomingHttpHeaders, IncomingMessage } from "node:http";

import { HttpError } from "./errors.js";

export type AuthKind = "none" | "internal" | "user";

export interface Reply {
  status: number;
  body?: unknown;
  text?: string;
  /** Raw bytes, for files such as PDFs. */
  raw?: Buffer;
  headers?: Record<string, string>;
}

export const json = (status: number, body?: unknown): Reply => ({ status, body });

export interface Ctx {
  method: string;
  url: URL;
  params: Record<string, string>;
  headers: IncomingHttpHeaders;
  /** The signed-in user. Always set on routes with auth "user". */
  userId: string | null;
  readJson(): Promise<unknown>;
  readBytes(maxBytes: number): Promise<Buffer>;
}

export function requireUser(ctx: Ctx): string {
  if (!ctx.userId) throw new HttpError(401, "unauthorized", "Sign in first.");
  return ctx.userId;
}

export interface RouteSpec {
  method: string;
  path: string; // like /api/folders/:id
  auth: AuthKind;
  handle: (ctx: Ctx) => Promise<Reply>;
}

interface CompiledRoute extends RouteSpec {
  pattern: RegExp;
  keys: string[];
}

export class Router {
  private readonly routes: CompiledRoute[] = [];

  add(...specs: RouteSpec[]): this {
    for (const spec of specs) {
      const keys: string[] = [];
      const source = spec.path.replace(/:([a-zA-Z]+)/g, (_match, key: string) => {
        keys.push(key);
        return "([^/]+)";
      });
      this.routes.push({ ...spec, pattern: new RegExp(`^${source}$`), keys });
    }
    return this;
  }

  match(method: string, pathname: string): { route: RouteSpec; params: Record<string, string> } | "method_not_allowed" | null {
    let pathMatched = false;
    for (const route of this.routes) {
      const found = route.pattern.exec(pathname);
      if (!found) continue;
      pathMatched = true;
      if (route.method !== method) continue;
      const params: Record<string, string> = {};
      route.keys.forEach((key, index) => {
        try {
          params[key] = decodeURIComponent(found[index + 1] ?? "");
        } catch {
          params[key] = ""; // a broken %-escape: treated as an id that does not exist
        }
      });
      return { route, params };
    }
    return pathMatched ? "method_not_allowed" : null;
  }
}

const tooLarge = (maxBytes: number) =>
  new HttpError(413, "too_large", `The upload is larger than the ${Math.max(1, Math.floor(maxBytes / 1024 / 1024))} MB limit.`);

/** Reads the whole request body, giving up as soon as it is larger than allowed. */
export async function readBody(req: IncomingMessage, maxBytes: number): Promise<Buffer> {
  if (Number(req.headers["content-length"] ?? 0) > maxBytes) throw tooLarge(maxBytes);
  const chunks: Buffer[] = [];
  let total = 0;
  for await (const chunk of req) {
    const piece = chunk as Buffer;
    total += piece.length;
    if (total > maxBytes) throw tooLarge(maxBytes);
    chunks.push(piece);
  }
  return Buffer.concat(chunks);
}

export async function readJsonBody(req: IncomingMessage, maxBytes = 64 * 1024): Promise<unknown> {
  const raw = await readBody(req, maxBytes);
  try {
    return JSON.parse(raw.toString("utf8"));
  } catch {
    throw new HttpError(400, "bad_json", "The request body must be JSON.");
  }
}

/** The body as an object (not null, not a list), or a 400. */
export function asObject(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new HttpError(400, "bad_json", "The request body must be a JSON object.");
  }
  return value as Record<string, unknown>;
}
