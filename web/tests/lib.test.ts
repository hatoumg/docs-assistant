import assert from "node:assert/strict";
import { test } from "node:test";

import { verifyToken } from "../../api/src/auth/jwt.ts";
import { signApiToken } from "../lib/apiToken.ts";
import { linkCitations, splitAnswer } from "../lib/citations.ts";
import { formatSize, scopeText } from "../lib/format.ts";

const SECRET = "s".repeat(40);
const USER = "2a22bdd8-dcc5-4e54-90fa-8198f0dc40c9";

test("a token signed by the website is accepted by the API", () => {
  assert.equal(verifyToken(signApiToken(USER, SECRET), SECRET), USER);
});

test("the API refuses a token with the wrong secret or that has expired", () => {
  assert.equal(verifyToken(signApiToken(USER, SECRET), "x".repeat(40)), null);
  const old = signApiToken(USER, SECRET, 60, () => Date.now() - 3600_000);
  assert.equal(verifyToken(old, SECRET), null);
});

test("citations become chips only when they point at a real passage", () => {
  const parts = linkCitations(splitAnswer("30 days [1] and 60 [7]. 【2】"), 2);
  assert.deepEqual(parts.filter((p) => p.type === "cite").map((p) => (p as any).number), [1, 2]);
  assert.ok(parts.some((p) => p.type === "text" && p.text === "[7]"));
});

test("sizes and scope text", () => {
  assert.equal(formatSize(512), "512 B");
  assert.equal(formatSize(2048), "2.0 KB");
  assert.equal(formatSize(5 * 1024 * 1024), "5.0 MB");
  assert.equal(scopeText(null), "all of your files");
  assert.equal(scopeText("Notes"), "“Notes” and everything inside it");
});
