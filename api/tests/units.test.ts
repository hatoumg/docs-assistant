import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { test } from "node:test";

import { signToken, verifyToken } from "../src/auth/jwt.js";
import { hashPassword, verifyPassword } from "../src/auth/password.js";
import { loadConfig } from "../src/config.js";
import { RateLimiter } from "../src/limits.js";
import { cleanFileName, cleanName, parseId, parseUuid } from "../src/validate.js";

const SECRET = "s".repeat(40);
const USER = "11111111-1111-1111-1111-111111111111";
const b64 = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");

// ----- tokens -----

test("a signed token gives back the user id", () => {
  assert.equal(verifyToken(signToken(USER, SECRET), SECRET), USER);
});

test("a token signed with another secret is refused", () => {
  assert.equal(verifyToken(signToken(USER, "x".repeat(40)), SECRET), null);
});

test("a token with a changed payload is refused", () => {
  const [head, , signature] = signToken(USER, SECRET).split(".");
  const forged = b64({ sub: "22222222-2222-2222-2222-222222222222", iss: "docs-assistant-web", aud: "docs-assistant-api", exp: 9999999999 });
  assert.equal(verifyToken(`${head}.${forged}.${signature}`, SECRET), null);
});

test("an expired token is refused, and a short delay is forgiven", () => {
  const issued = Date.parse("2026-01-01T00:00:00Z");
  const token = signToken(USER, SECRET, 60, () => issued);
  assert.equal(verifyToken(token, SECRET, () => issued + 62_000), USER);
  assert.equal(verifyToken(token, SECRET, () => issued + 70_000), null);
});

test("a token issued in the future is refused", () => {
  const token = signToken(USER, SECRET, 60, () => Date.parse("2026-01-01T01:00:00Z"));
  assert.equal(verifyToken(token, SECRET, () => Date.parse("2026-01-01T00:00:00Z")), null);
});

test("the 'none' algorithm and other algorithms are refused", () => {
  const payload = b64({ sub: USER, iss: "docs-assistant-web", aud: "docs-assistant-api", exp: 9999999999 });
  assert.equal(verifyToken(`${b64({ alg: "none", typ: "JWT" })}.${payload}.`, SECRET), null);
  const head = b64({ alg: "HS512", typ: "JWT" });
  const signature = createHmac("sha512", SECRET).update(`${head}.${payload}`).digest("base64url");
  assert.equal(verifyToken(`${head}.${payload}.${signature}`, SECRET), null);
});

test("a token for another audience, or with no real user id, is refused", () => {
  const head = b64({ alg: "HS256", typ: "JWT" });
  const make = (claims: object) => {
    const payload = b64(claims);
    return `${head}.${payload}.${createHmac("sha256", SECRET).update(`${head}.${payload}`).digest("base64url")}`;
  };
  const good = { sub: USER, iss: "docs-assistant-web", aud: "docs-assistant-api", exp: Math.floor(Date.now() / 1000) + 60 };
  assert.equal(verifyToken(make(good), SECRET), USER);
  assert.equal(verifyToken(make({ ...good, aud: "someone-else" }), SECRET), null);
  assert.equal(verifyToken(make({ ...good, iss: "someone-else" }), SECRET), null);
  assert.equal(verifyToken(make({ ...good, sub: "admin" }), SECRET), null);
  assert.equal(verifyToken(make({ ...good, exp: "tomorrow" }), SECRET), null);
});

test("garbage is refused without throwing", () => {
  for (const junk of ["", "abc", "a.b", "a.b.c", "....", "%%%.%%%.%%%"]) assert.equal(verifyToken(junk, SECRET), null);
});

// ----- passwords -----

test("a password verifies, and a wrong one does not", async () => {
  const stored = await hashPassword("correct horse battery");
  assert.match(stored, /^scrypt\$/);
  assert.equal(await verifyPassword("correct horse battery", stored), true);
  assert.equal(await verifyPassword("correct horse batterz", stored), false);
});

test("the same password hashes differently each time", async () => {
  assert.notEqual(await hashPassword("same password"), await hashPassword("same password"));
});

test("a damaged stored hash never verifies", async () => {
  assert.equal(await verifyPassword("x", ""), false);
  assert.equal(await verifyPassword("x", "plaintext"), false);
  assert.equal(await verifyPassword("x", "bcrypt$1$2$3$4$5"), false);
});

// ----- limiter -----

test("the limiter blocks after the allowance and recovers as the window slides", () => {
  let now = 0;
  const limiter = new RateLimiter(3, 1000, () => now);
  assert.equal(limiter.take("a"), true);
  assert.equal(limiter.take("a"), true);
  assert.equal(limiter.take("a"), true);
  assert.equal(limiter.take("a"), false);
  assert.equal(limiter.take("b"), true); // other keys are separate
  now = 1001;
  assert.equal(limiter.take("a"), true);
});

test("reset clears a key", () => {
  const limiter = new RateLimiter(1, 1000, () => 0);
  limiter.record("a");
  assert.equal(limiter.isBlocked("a"), true);
  limiter.reset("a");
  assert.equal(limiter.isBlocked("a"), false);
});

// ----- config -----

const goodEnv = { API_JWT_SECRET: "a".repeat(40), INTERNAL_SECRET: "b".repeat(40), RAG_SERVICE_SECRET: "c".repeat(40) };

test("config reads the secrets and has sensible defaults", () => {
  const config = loadConfig(goodEnv);
  assert.equal(config.port, 4000);
  assert.equal(config.ragServiceUrl, "http://127.0.0.1:8000");
  assert.equal(config.maxUploadBytes, 10 * 1024 * 1024);
});

test("missing, short, placeholder or repeated secrets stop the API from starting", () => {
  assert.throws(() => loadConfig({}), /API_JWT_SECRET/);
  assert.throws(() => loadConfig({ ...goodEnv, INTERNAL_SECRET: "short" }), /INTERNAL_SECRET/);
  assert.throws(() => loadConfig({ ...goodEnv, RAG_SERVICE_SECRET: "change-me" + "x".repeat(40) }), /RAG_SERVICE_SECRET/);
  assert.throws(() => loadConfig({ ...goodEnv, INTERNAL_SECRET: goodEnv.API_JWT_SECRET }), /different/);
});

// ----- validation -----

test("ids in addresses: bad ones are 'not found'", () => {
  assert.equal(parseUuid("AAAAAAAA-1111-2222-3333-444444444444"), "aaaaaaaa-1111-2222-3333-444444444444");
  assert.throws(() => parseUuid("../etc/passwd"), { status: 404 });
  assert.throws(() => parseUuid(undefined), { status: 404 });
  assert.equal(parseId("42"), 42);
  for (const bad of ["0", "-1", "1.5", "abc", "99999999999", ""]) assert.throws(() => parseId(bad), { status: 404 });
});

test("names are trimmed and refuse slashes and control characters", () => {
  assert.equal(cleanName("  Contracts 2024 ", "Name"), "Contracts 2024");
  for (const bad of ["", "   ", "a/b", "a\\b", "a\nb", "x".repeat(121)]) assert.throws(() => cleanName(bad, "Name"), { status: 400 });
  assert.throws(() => cleanName(5, "Name"), { status: 400 });
});

test("only .md, .txt and .pdf file names are accepted, in any capitalisation", () => {
  assert.deepEqual(cleanFileName("Notes.MD"), { name: "Notes.MD", extension: ".md" });
  assert.deepEqual(cleanFileName("a.b.txt"), { name: "a.b.txt", extension: ".txt" });
  assert.deepEqual(cleanFileName("Report.PDF"), { name: "Report.PDF", extension: ".pdf" });
  for (const bad of ["a", ".md", "a.md.exe", "a.docx"]) assert.throws(() => cleanFileName(bad), { status: 415 });
});
