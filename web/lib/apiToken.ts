import { createHmac } from "node:crypto";

/**
 * Signs the short-lived token the website sends to the API with each request, naming the signed-in user.
 * The API checks it with the same secret (API_JWT_SECRET). Server-side only: the secret never reaches the browser.
 */
const ISSUER = "docs-assistant-web";
const AUDIENCE = "docs-assistant-api";

const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");

export function signApiToken(userId: string, secret: string, ttlSeconds = 60, now = () => Date.now()): string {
  const issuedAt = Math.floor(now() / 1000);
  const header = encode({ alg: "HS256", typ: "JWT" });
  const payload = encode({ sub: userId, iss: ISSUER, aud: AUDIENCE, iat: issuedAt, exp: issuedAt + ttlSeconds });
  const signature = createHmac("sha256", secret).update(`${header}.${payload}`).digest("base64url");
  return `${header}.${payload}.${signature}`;
}
