import { createHmac, timingSafeEqual } from "node:crypto";

/**
 * The website signs a short-lived token for each request it forwards, naming the signed-in user.
 * HS256 only: the algorithm in the token is checked, never trusted ("none" and other algorithms are refused).
 */
const ISSUER = "docs-assistant-web";
const AUDIENCE = "docs-assistant-api";
const LEEWAY_SECONDS = 5;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
const sign = (data: string, secret: string) => createHmac("sha256", secret).update(data).digest();

export function signToken(userId: string, secret: string, ttlSeconds = 60, now = () => Date.now()): string {
  const issuedAt = Math.floor(now() / 1000);
  const header = encode({ alg: "HS256", typ: "JWT" });
  const payload = encode({ sub: userId, iss: ISSUER, aud: AUDIENCE, iat: issuedAt, exp: issuedAt + ttlSeconds });
  return `${header}.${payload}.${sign(`${header}.${payload}`, secret).toString("base64url")}`;
}

/** Returns the user id, or null if the token is missing, forged, expired or meant for someone else. */
export function verifyToken(token: string, secret: string, now = () => Date.now()): string | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const [header, payload, signature] = parts as [string, string, string];
  try {
    const head = JSON.parse(Buffer.from(header, "base64url").toString("utf8"));
    if (head?.alg !== "HS256") return null;

    const expected = sign(`${header}.${payload}`, secret);
    const given = Buffer.from(signature, "base64url");
    if (given.length !== expected.length || !timingSafeEqual(given, expected)) return null;

    const claims = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    const nowSeconds = Math.floor(now() / 1000);
    if (claims?.iss !== ISSUER || claims?.aud !== AUDIENCE) return null;
    if (typeof claims.exp !== "number" || claims.exp + LEEWAY_SECONDS < nowSeconds) return null;
    if (typeof claims.iat === "number" && claims.iat - LEEWAY_SECONDS > nowSeconds) return null;
    if (typeof claims.sub !== "string" || !UUID.test(claims.sub)) return null;
    return claims.sub.toLowerCase();
  } catch {
    return null;
  }
}
