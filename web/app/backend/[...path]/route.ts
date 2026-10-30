import { auth } from "@/auth";
import { signApiToken } from "@/lib/apiToken";
import { apiUrl } from "@/lib/serverApi";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * The only way the browser reaches the API. It checks the signed-in session, refuses requests from other sites,
 * and adds a short-lived token naming the user, so the browser never holds an API credential.
 */
const ALLOWED = new Set(["folders", "files", "chat", "me"]);
const MAX_BODY = 11 * 1024 * 1024; // a little above the API's 10 MB file limit

const reply = (status: number, message: string) => Response.json({ error: "error", message }, { status });

async function forward(request: Request, context: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await context.params;
  if (!path.every((part) => /^[A-Za-z0-9_-]+$/.test(part)) || !ALLOWED.has(path[0] ?? "")) return reply(404, "Not found.");

  const session = await auth();
  if (!session?.user?.id) return reply(401, "Please sign in again.");

  if (request.method !== "GET") {
    const origin = request.headers.get("origin");
    const host = request.headers.get("host");
    if (!origin || !host || new URL(origin).host !== host) return reply(403, "Request refused.");
  }

  const secret = process.env.API_JWT_SECRET;
  if (!secret) return reply(500, "API_JWT_SECRET is not set in the .env file.");

  let body: ArrayBuffer | undefined;
  if (request.method === "POST") {
    if (Number(request.headers.get("content-length") ?? 0) > MAX_BODY) return reply(413, "That is too large.");
    body = await request.arrayBuffer();
    if (body.byteLength > MAX_BODY) return reply(413, "That is too large.");
  }

  const search = new URL(request.url).search;
  const headers: Record<string, string> = { authorization: `Bearer ${signApiToken(session.user.id, secret)}` };
  const type = request.headers.get("content-type");
  if (type) headers["content-type"] = type;

  let upstream: Response;
  try {
    upstream = await fetch(`${apiUrl()}/api/${path.join("/")}${search}`, { method: request.method, headers, body, cache: "no-store" });
  } catch {
    return reply(502, "The API is not running. Start it with: npm run dev (in the api folder).");
  }
  const out = new Headers();
  for (const name of ["content-type", "content-disposition"]) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  return new Response(upstream.status === 204 ? null : upstream.body, { status: upstream.status, headers: out });
}

export { forward as GET, forward as POST, forward as DELETE };
