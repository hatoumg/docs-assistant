import { createHash, timingSafeEqual } from "node:crypto";
import type { IncomingMessage, ServerResponse } from "node:http";

import { verifyToken } from "./auth/jwt.js";
import type { Config } from "./config.js";
import type { Db } from "./db.js";
import { HttpError } from "./errors.js";
import { json, readBody, readJsonBody, Router, type Ctx, type Reply } from "./http.js";
import { RateLimiter } from "./limits.js";
import type { RagClient } from "./ragClient.js";
import { chatRoutes } from "./routes/chat.js";
import { fileRoutes } from "./routes/files.js";
import { folderRoutes } from "./routes/folders.js";
import { internalRoutes } from "./routes/internal.js";
import { getUser } from "./store/users.js";

export interface Deps {
  config: Config;
  db: Db;
  rag: RagClient;
  now?: () => number;
}

const sameSecret = (given: string, expected: string) =>
  timingSafeEqual(createHash("sha256").update(given).digest(), createHash("sha256").update(expected).digest());

export function createApp({ config, db, rag, now = Date.now }: Deps) {
  const loginLimiter = new RateLimiter(5, 15 * 60_000, now); // 5 wrong passwords per email per 15 minutes
  const chatLimiter = new RateLimiter(20, 60_000, now); // 20 questions per user per minute

  const router = new Router().add(
    { method: "GET", path: "/health", auth: "none", handle: async () => json(200, { ok: true }) },
    {
      method: "GET",
      path: "/api/me",
      auth: "user",
      handle: async (ctx) => json(200, { user: await getUser(db, ctx.userId!) }),
    },
    ...internalRoutes(db, loginLimiter),
    ...folderRoutes(db, config.uploadDir),
    ...fileRoutes(db, rag, config),
    ...chatRoutes(db, rag, chatLimiter),
  );

  /** Who is calling? Throws 401 unless the route's kind of credential is present and valid. */
  async function authenticate(kind: "none" | "internal" | "user", req: IncomingMessage): Promise<string | null> {
    if (kind === "none") return null;
    if (kind === "internal") {
      const given = String(req.headers["x-internal-secret"] ?? "");
      if (!sameSecret(given, config.internalSecret)) throw new HttpError(401, "unauthorized", "Not allowed.");
      return null;
    }
    const header = String(req.headers.authorization ?? "");
    const userId = header.startsWith("Bearer ") ? verifyToken(header.slice(7), config.apiJwtSecret, now) : null;
    // The token alone is not enough: the account must still exist.
    if (!userId || !(await getUser(db, userId))) throw new HttpError(401, "unauthorized", "Sign in first.");
    return userId;
  }

  async function handle(req: IncomingMessage): Promise<Reply> {
    const url = new URL(req.url ?? "/", "http://localhost");
    const method = req.method ?? "GET";
    const matched = router.match(method, url.pathname);
    if (matched === null) throw new HttpError(404, "not_found", "No such page.");
    if (matched === "method_not_allowed") throw new HttpError(405, "method_not_allowed", "That method is not allowed here.");

    const userId = await authenticate(matched.route.auth, req);
    const ctx: Ctx = {
      method,
      url,
      params: matched.params,
      headers: req.headers,
      userId,
      readJson: () => readJsonBody(req),
      readBytes: (maxBytes) => readBody(req, maxBytes),
    };
    return matched.route.handle(ctx);
  }

  return async function listener(req: IncomingMessage, res: ServerResponse): Promise<void> {
    let reply: Reply;
    let closeAfter = false;
    try {
      reply = await handle(req);
    } catch (error) {
      if (error instanceof HttpError) {
        reply = json(error.status, { error: error.code, message: error.message });
        closeAfter = error.status === 413; // stop reading an oversized upload
      } else {
        console.error("Unexpected error:", error);
        reply = json(500, { error: "internal", message: "Something went wrong on the server." });
      }
    }

    const headers: Record<string, string> = { "x-content-type-options": "nosniff", "cache-control": "no-store", ...reply.headers };
    if (closeAfter) headers.connection = "close";
    let payload: string | Buffer | undefined;
    if (reply.raw !== undefined) {
      payload = reply.raw;
    } else if (reply.text !== undefined) {
      payload = reply.text;
    } else if (reply.body !== undefined) {
      payload = JSON.stringify(reply.body);
      headers["content-type"] = "application/json; charset=utf-8";
    }
    res.writeHead(reply.status, headers);
    res.end(payload);
    if (closeAfter) res.on("finish", () => req.destroy());
  };
}
